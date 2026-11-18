# StudyLIVE2-coord: the live round-1 coordinator and its eight arms

Status: ENGINEERING TASK, built and tested on flash (CPU only), 2026-11-17.
Pre-registration: `research/EXPERIMENTS.md` row `StudyLIVE2-coord` (ENGINEERING TASK,
user-authorized 2026-11-17, CPU only on flash, NO MEASUREMENT).
Authority: `research/policy_design_log.md` (D56, D62-D94) and `research/policy_spec_v4.md`.

**NOTHING IN THIS REPORT IS A MEASUREMENT.** Every number here comes from the CPU stub
(`experiments/orchestration/live/fake_server.py`) or from a `--dry-run` with no server at all,
on a SYNTHETIC trace. Every run header carries `is_measurement: false`. The quantities that mean
anything are the coordinator's OWN: decision latency, CPU use, request rate, and whether each
arm's actions are legal.

---

## 1. What was built

```
experiments/orchestration/live2/
  schema.py            the shared fleet <-> coordinator interface (dataclasses + JSONL)
  CONTRACT.md          what every field means
  cachekeys.py         D84 per-device cache salt and per-(device, frame) mm uuid
  bodies.py            the request body: the committed StudyRH7 wire form plus cache_salt
  backend.py           Live2Backend(HttpBackend): the live2 body, usage parsing, sent-body record
  calib.py             D86 calibration load, INTERIM labelling, refusal, a/b -> knots
  cstate.py            coordinator state and the interface.Observation every arm sees
  armbase (in arms.py) the declarations the run loop reads off an arm
  arms.py              arms 2-8
  arms_policy.py       arm 1, the policy core
  coordinator.py       the run loop
  traces.py            SYNTHETIC trace, fleet-trace loader, D96 fairness digest, pull responder
  bridge.py            the coordinator as the fleet emulator's Coordinator Protocol
  joiner.py            D63 predicted versus actual
  run_live2_cell.py    the CLI for one cell
  scale_smoke.py       test (i)
  tests/test_live2_coord.py        tests a-h, no server
  tests/test_live2_fakeserver.py   the tests that need the CPU stub
```

CONCURRENCY. The loop is a single-threaded event loop over a fine grid with HTTP concurrency
from the existing `HttpBackend`'s thread pool and its background `/metrics` poller, which is the
StudyLIVE1 adapter pattern; it is not `asyncio`. The effect the brief asks for is the one that
matters and is met: a decision epoch never waits on HTTP, and a completion is collected at the
next epoch.

The coordinator is a pure HTTP client of an OpenAI-compatible server, built on the EXISTING
`experiments/orchestration/live/adapter.py::HttpBackend` (thread pool, `/metrics` poller, stream
read that times the first token). `adapter.py` itself is UNCHANGED; the live2 subclass adds
`post_live2`, because live2 sends the committed StudyRH7 wire form plus D84's `cache_salt`
instead of StudyLIVE1's token-count placeholder body, and overrides `post` to RAISE so the
placeholder body (which carries no salt and no uuids) can never be sent by accident.

Nothing under `experiments/orchestration/policy/`, nor `constructed.py`, `interface.py`,
`registry.yaml`, the frozen pol4 cost model, nor any earlier result was modified.

## 2. The eight arms and where each comes from

| # | arm | source | action space |
|---|---|---|---|
| 1 | `policy-core` | spec v4 CORE (D66) via `experiments/orchestration/policy/` | admission, release, piece size, session actions, order |
| 2 | `device-only` | `baselines/naive.py::DeviceOnly` AS COMMITTED | sends nothing |
| 3 | `always-cloud-fcfs` | `baselines/naive.py::AlwaysCloudFCFS` AS COMMITTED (the existing port) | one request per opportunity |
| 4 | `edf` | pi_0 standalone: ordering by `policy/rollout.py::Rollout._edf`, one unit per epoch, rebuilds WHOLE | as 1 |
| 5 | `edf-piece1024` | pi_0 with `slice_tokens = 1024` | as 1 |
| 6 | `edf-piece2048` | pi_0 with `slice_tokens = 2048` | as 1 |
| 7 | `utility-per-cost` | `baselines/constructed.py::B8UtilityPerGPUSecond` AS COMMITTED | streams, recall |
| 8 | `b9` | `baselines/constructed.py::B9BestOfBreed` AS COMMITTED | streams, recall, sessions, order |

Every arm is an `interface.Policy`, so all eight share ONE action space and every action passes
`interface.validate_action` while every observation passes `interface.scrub`, both inside
`Policy.__call__`. `interface.check_fairness` runs before the run and an arm declaring
`reads_future` is refused.

**B9 is used as committed.** Its amendment-2 fix (the VideoStorm demand read-back, A4b / A5b) is
already applied in `constructed.py`; the subclass `B9Arm` sets the live2 name and nothing else,
and does not override `decide`. The run loop honours DEFER (D90) for every arm, including the
ones that never emit it. D90's correction of D65 is reflected: the cascade floor, the
device-answer charge and the HybridLLM leak were amendment-2 fixes to OTHER arms and the
harness, not to B9, and nothing was changed in B9 on their account.

**How arm 4 differs from the registry's `edf-service-time`** (`baselines/naive.py:178`, which is
a different arm and is NOT one of the eight):

* `edf-service-time` applies an ADMISSION FILTER (a query reaches the cloud only if
  `costs.recall_ttft_s` at its readiness fits its remaining slack, else DEVICE). pi_0 has no
  admission test and declines nothing for not fitting.
* `edf-service-time` never materializes, so a cold history is answered by one request at COLD
  readiness. pi_0 explicitly MATERIALIZEs, whole (arm 4) or in a fixed piece (arms 5, 6).
* `edf-service-time` orders only the recall queries and leaves streams at the documented
  default. pi_0 orders ONE merged pending set (monitoring calls, rebuild pieces, recall answers)
  and releases ONE unit per decision epoch, which is what spec 3.5 defines pi_0 to be.

**Arms charged StudyD8's 0.567 s device-answer rule (D87): none.** All eight declare
`reads_device_answer = False` (checked programmatically; B9 included). The charge is implemented
in the run loop anyway, both as a visibility delay and as the delivery time of a DEVICE outcome,
so an arm that does declare it is charged automatically. It is UNEXERCISED by these eight.

**What the policy-core arm has on, and off (D66).** ON: admission (8.1), the release
coordinator (8.2), recall-job continuation and feasibility (8.3), rollout-chosen piece size
(8.4), residency bookkeeping (7.6 / RES1), per-device deficit counters (8.6), per-tier
calibration (3.2), outage handling (8.5). OFF: every conditional mechanism, through
`policy/flags.py`, whose flags all default off (D38); the arm REFUSES to configure if any is on.
Monitoring is capacity-based (D62), so the trigger family is the library's
`DeviceFilter(threshold=0.0)` default, which escalates every instant and leaves the choice to
admission and the release loop; ONE escalation per decision INSTANT, not per epoch.

Residency uses `policy/residency_belief.py::ResidencyBelief`, StudyRES1's MEASURED rule (4-class
tier accuracy 0.9946 on StudyENG1c) with its boundary split, passed to both the `Rollout` and
the `Coordinator`, instead of `tiers.p_host_from_occupancy` whose eviction order is an
explicitly labelled ASSUMPTION. Its cap is the host capacity INPUT (D56), so a different
capacity scales the boundary margin rather than changing the rule. A completed build calls
`note_build` on that history's prefix and every other completed request calls `note_write`.

## 3. vLLM 0.31.0 cache-isolation evidence (D84)

Source inspected: the `vllm-0.31.0-cp38-abi3-manylinux_2_28_x86_64.whl` from PyPI, unpacked
read-only into a scratch directory outside the repo. Nothing was installed into any project
environment. Both mechanisms D84 needs exist in 0.31.0.

**(1) Per-device cache salt.**

| what | file and line |
|---|---|
| the request field | `vllm/entrypoints/openai/chat_completion/protocol.py:456-467`: `cache_salt: str \| None = Field(default=None, min_length=1, max_length=1024, ...)` on `ChatCompletionRequest`, with the validator at `:513-518` |
| it reaches the engine request | `vllm/v1/request.py:73`, `:185`, `:260` (`cache_salt=request.cache_salt`) |
| it enters the prefix-cache key | `vllm/v1/core/kv_cache_utils.py:636-640`, inside `generate_block_hash_extra_keys` (`:613-651`): `[("cache_salt", request.cache_salt)] if (start_token_idx == 0 and request.cache_salt)` |
| the whole chain is salted, not only block 0 | `vllm/v1/core/kv_cache_utils.py:684-713`, `hash_block_tokens(..., parent_block_hash, ...)`: each block hash includes its parent's, so salting block 0 propagates to every later block |

**(2) Multimodal uuid per (device, frame).**

| what | file and line |
|---|---|
| a chat content part may carry `uuid` | `vllm/entrypoints/chat_utils.py:1711` (`uuid = part.get("uuid", None)`) and `:1726-1733` (the `image_url` branch taken when a uuid is present, including `"image_url": {"url": ...}` and `"image_url": null`) |
| it is passed through the parser | `vllm/entrypoints/chat_utils.py:982`, `:1077-1078`, `:1276-1278` (`parse_image(image_url, uuid)`) |
| collected per modality | `vllm/entrypoints/chat_utils.py:838-839`, then set as `prompt["multi_modal_uuids"]` at `:1078-1079` |
| documented semantics | `vllm/inputs/llm.py:88-95`: "non-None entries override the default hashes for caching, and MUST be unique per multimodal item" |
| the uuid BECOMES the mm hash | `vllm/multimodal/processing/inputs.py:34-108`, in particular `:90-105`: with no extra hash factors the client uuid is used verbatim as the item's hash |
| that hash is the prefix-cache mm key | `vllm/v1/core/kv_cache_utils.py:552`: `extra_keys.append(("mm", mm_feature.identifier, offset - start_token_idx))` |

So two devices replaying the same clip share neither KV nor image encoding, while a device
re-sending its own frame with the same uuid still hits its own cache, which is exactly what D84
requires. The uuid namespace is the committed StudyRH7 / SLICE1 / ENG1c convention
(`experiments/cost/study_rh7_eager_lazy.py:72-78, 90, 121`):
`"<run_tag>|<device_id>|<session_id>|<frame_ref>"`.

**Real-engine verification procedure (an H100 task, NOT done here).** Before any measured run:
1. Start the round-1 server (vLLM 0.31.0, prefix caching ON, the round-1 KV pool and host
   offload), and confirm `/metrics` is reachable.
2. Pick one clip. Send it as device `A` with `cache_salt = salt(A)` and uuids
   `tag|A|sess|frame`. Record `usage.prompt_tokens_details.cached_tokens` (expected 0 on the
   first send).
3. Send the SAME clip immediately as device `B`, with `salt(B)` and uuids `tag|B|sess|frame`.
   **Required result: `cached_tokens == 0`.** Any non-zero value means the isolation failed and
   no measured run may start.
4. Send the same clip AGAIN as device `A`, unchanged. **Required result: `cached_tokens > 0`**,
   which proves the salt isolates devices without destroying within-device reuse.
5. Repeat 2-4 with a 30 s history append (`delta` mode: uuid-only references for the already
   sent frames, bytes for the new ones) to check that the mm-cache path, not only the KV path,
   is isolated: `A`'s second append must report `cached_tokens` covering its prefix, and `B`'s
   first append on the same frames must report 0.
6. Record all six numbers in the round-1 report beside the server's git/version string.

On the CPU stub this cannot be checked end to end, because the stub reports no
`prompt_tokens_details.cached_tokens`. The build therefore tests that the FIELDS ARE SENT, on
the bodies that actually went out (test f), and `backend.cached_tokens_of` returns `None`, never
0, when the server does not report it, so D81's WARM / COLD tag is never fabricated.

## 3b. D96: opportunity ids and the fairness digest

Implemented mid-build on the user's ruling, against D95 and D96 as committed in
`research/policy_design_log.md`. D96 resolves a conflict StudyLIVE2 found between this
`CONTRACT.md` and the fleet side; it is an implementation ruling, not a methodological change.

**Part 1, opportunity ids.** `opportunity_id` is now a REQUIRED field on `monitor_offer`,
`monitor_frame` and `recall_question`, unique within the run and ASSIGNED BY THE TRACE
GENERATOR. The coordinator copies it unchanged into `cloud_answer`, into the decision log's
`opportunity_ids` and into the request log, and NEVER constructs, derives or parses one: a bare
`instant_id` or `question_id` is ambiguous once D84 allows a clip or a session to be replayed on
more than one device, or twice on one device. `Opportunity.opp_id` IS that id, so every lookup
in the coordinator is by it; `instant_id` and `question_id` travel alongside, because they are
what the device and the recordings call the same thing, and the mode-B `pull_request` carries
the `instant_id` as the brief specifies. The CONTRACT.md sentence saying the `opportunity_id` on
a `cloud_answer` is the `instant_id` or `question_id` it answers has been REMOVED, as D96
requires.

Field lists, which `fleet/events.py::check_against_schema()` confirms are identical to the
fleet's (`field lists identical`, `d96_pending: False`):

```
monitor_offer    (device_id, opportunity_id, instant_id, t_capture, deadline_s, frame_bytes)
monitor_frame    (device_id, opportunity_id, instant_id, t_capture, t_arrive, deadline_s,
                  frame_ref, frame_bytes)
recall_question  (device_id, opportunity_id, session_id, question_id, t_ask, t_arrive,
                  deadline_s, question, options)
```

**Part 2, the fairness digest.** The canonical digest is the FLEET's: an order-independent
sha256 over sorted event tuples, the full 64 hex characters, never a prefix taken in iteration
order. Coverage is `device_register`, `session_start`, `session_end`, `history_append`,
`recall_question`, and `monitor_offer` in PULL mode or `monitor_frame` in PUSH mode; in pull
mode the frames are excluded because which frames exist depends on the arm's own pulls. It is
recorded as `fairness_digest` in every run header and in every `result.json`, and it is what the
fairness test compares across arms. The StudyLIVE1-port digest survives ONLY as
`live1_trace_digest`; the header no longer has a `trace_digest` key at all, so neither can be
presented as the other.

The row shape is not reinvented: `traces._fairness_row` reproduces
`fleet/trace.py::_digest_tuple` field for field, and a test asserts BYTE EQUALITY between
`traces.fairness_digest` and `fleet/trace.py::fairness_digest` on the same stream in BOTH modes
(it passes), so a future change to either side fails loudly instead of letting two digests
diverge silently. The wire events carry the time under their own names, and the mapping onto the
fleet's single `t` is: `start_t` for a registration, `t` for a session boundary, `t_arrive` for
a history batch, `t_ask` for a question, `t_capture` for a monitoring instant.

## 4. The shared interface

`live2/schema.py` is the single definition; `live2/CONTRACT.md` says what each field means. The
event field lists are exactly those in the brief, including `session_start` and `session_end`
(D83). `live2/fleet/events.py::check_against_schema()` reports `field lists identical` against
it (checked after subagent B added the two session events on its side).

Three JSONL log streams per run (`decision`, `request`, `residency`) and a `header.json` whose
contents are listed in section 8.

## 5. mu handling (D72 as amended by D88)

| version | how | what is logged |
|---|---|---|
| `--mu-mode none` | `params.mu = 0`, `mu_estimator = "none"` | `mu = 0` on every decision; the backlog channel is silent and says so |
| `--mu-mode ewma` | `mu_estimator = "ewma_marginal_utility"` | `mu` on every decision AND the run's TIME-AVERAGED mu in `result.json` (`mu_time_average`), because D88 sets the two fixed versions to x0.5 and x2 of it over the pilot |
| `--mu-mode fixed --mu-fixed V` | `params.mu = V`, estimator off | `mu = V` on every decision |

`--mu-mode fixed` without `--mu-fixed` is refused with the D88 reason (no committed DEV value
for utility per GPU-second exists, so the value comes from the pilot's EWMA average). H is
`--h`, swept at 0.5 and 1.0 s.

Spec v4 section 3.5 says mu = 0 "silences the backlog channel ... so no evaluation may run with
it". D72 and D88 nevertheless make mu = 0 one of the four labelled round-1 versions, as the
reference. The spec's own header says the log is the record where the two disagree, so mu = 0 is
allowed and is labelled a reference version, not a result.

## 6. Placeholder table (D73), all "not tuned"

| parameter | value | note |
|---|---|---|
| H | 0.5 / 1.0 s | swept (D73); `--h` |
| feasibility threshold | 0.5 | D73; jobs given up on are reported (`arm_stats.jobs_infeasible`) |
| belief conservatism | 0.5 | `params.py` default; belief errors reported |
| H_s (state horizon) | 60.0 s | D73 |
| monitoring answer window | 1.0 s | tied to the dashcam deadline (D71, D73) |
| prefix-loss re-plan threshold | 0.5 | `params.py` default; firings reported (`arm_stats.prefix_loss_replans`) |
| mu EWMA alpha | 0.1 | `params.py` default; our choice |

Every PLACEHOLDER field of `policy/params.py` is additionally dumped into `result.json`
(`placeholders`) with its value and `tuned: false`, so the round-1 report can list them all.

Fixed by decision, not placeholders: omega_SH = 1.0 and omega_RC = 0.4246 (D89, the `params.py`
PROPOSAL); omega_SS stays `None` (no SS traffic, P2). Cost model `pol4` by default, pluggable
with `--cost-model` over `ENGINE_MODELS = ("eng1", "pol4", "pol4_nobatch")` (D74; pol6 did not
pass its one-shot before this build, so pol4 stands).

## 7. Predicted versus actual (D63)

`live2/joiner.py` joins the three streams into one row per (decision, request) pair, tagged with
the traffic mix in flight at submit time (`{monitor, piece, whole, recall}` counts), and one row
per affected request for the predicted imposed delay. A baseline's `predicted` block is empty
and the joiner marks those rows `predicted_by: "none"` rather than reading a missing prediction
as a prediction of zero.

The policy arm's prediction for a release is the spec's own counterfactual: two rollouts, one
with the item released now and one with it deferred, from the state the release loop actually
sees (after admission, before the release loop). `ttft_s` and `completion_s` come from the
released item's own delivery; `imposed_delay_s_by_request` is the DIFFERENCE in every other
item's predicted delivery between the two rollouts. Predictions are computed for at most
`predict_log_max = 4` released items per epoch, because each one costs two extra rollouts
(M4: 0.34 ms per DeltaJ evaluation, and the release loop is already quadratic in the pending
set).

## 8. Reproducibility: the run header

`header.json` carries the D73 PLACEHOLDER TABLE (31 rows for the policy arm, each with its
value and `tuned: false`), and `git_commit`, `arm`, `arm_version`, every flag value, `gpu_kv_tokens`,
`host_tier_gib`, `host_tier_tokens`, `cost_model_id`, `cost_model_hash` (an md5 over the
StudyPOL4 freeze file list plus the model name), `calibration_file`, `calibration_label`,
`fairness_digest` (D96), `live1_trace_digest`, `trace_label`, `seed`, `targets`, `upload_mode`, `mu_mode`, `mu_value`, `H`,
`tick_s`, `server_url`, `server_kind`, `model` (the served model id; `--model` sets it for a real run), `schema_version` and `is_measurement`.

Capacities are INPUTS (D56, D76): `--gpu-kv-tokens` and `--host-tier-gib` are REQUIRED on the
command line and are passed to every arm that uses them; the policy arm refuses to configure
with either at zero. Targets (D71, D82) are passed to all arms identically and are never changed
per arm: dashcam L = 1.0 s, p = 25 % per device; robot L = 5.0 s, p = 90 % POOLED.

Ticking: the policy arm ticks at H; arms without H tick at **50 ms**, recorded in the header.
Every arm is additionally called ON EVERY EVENT, on a 50 ms event grid, so an H = 1 s arm still
decides about an instant that arrived 40 ms ago instead of missing a 1.0 s deadline by
construction.

## 9. Test results (flash, CPU only)

`python3 tests/test_live2_coord.py` - 26 tests, OK (11 s). `python3
tests/test_live2_fakeserver.py` - 4 tests, OK (70 s).

| test | what it asserts | result |
|---|---|---|
| a | schema round-trip for every event kind, JSONL round-trip, header round-trip | PASS |
| a | all 8 arms run end to end and emit only legal actions (`validate_action` inside `Policy.__call__`), zero errors | PASS |
| bridge | the coordinator is driven through the FLEET EMULATOR's Protocol (`on_event`, `tick`): cloud answers come back on-schema, pull mode replies with `pull_request`, an off-schema event is refused at the bridge | PASS |
| chain | at StudyENG1's 11,184-token D2 history: a 1,024-token chain completes in 11 pieces summing to 11,184; `slice_tokens = None` is ONE request; a later piece carries uuid REFERENCES for the already sent frames instead of their bytes | PASS |
| b | the canonical D96 fairness digest is 64 hex, order-independent, mode-aware, BYTE-IDENTICAL to `fleet/trace.py::fairness_digest` in both modes, and identical for all 8 arms; it changes with the stream | PASS |
| c | `scrub` runs on every observation and no forbidden field is reachable; an arm declaring `reads_future` is REFUSED before any submission | PASS |
| d | `device-only` submits 0 requests; `always-cloud-fcfs` submits exactly one per opportunity (486 of 486) | PASS |
| e | same trace + arm + seed gives an identical decision log for `edf`, `edf-piece2048`, `b9` and `policy-core`, excluding `decision_latency_ms` | PASS |
| f | every request carries a non-empty `cache_salt` and one mm uuid per frame; devices never share a salt or a uuid; the same (device, frame) keeps ONE uuid across re-sends; the wire body carries the fields and a uuid-only reference has `image_url: null` | PASS |
| g | a deferred item is not submitted before `defer_s` has elapsed, and is submitted afterwards | PASS |
| h | the committed `orin2_calibration.json` is labelled INTERIM, is allowed against the stub and REFUSED against a real server; a file declaring `label: FINAL` + `fit_sample: dense` is allowed; a SYNTHETIC trace is refused against a real server | PASS |
| fake server | requests reach the stub and return HTTP 200 with a first token; `cache_path` is `None` because the stub reports no `cached_tokens`; mode B pulls before the frame exists; the policy core runs live with `cost_model_id = pol4`, `H = 1.0`, `mu = 0` on every decision | PASS |

Determinism (test e) is checked in `--dry-run`, which sends no HTTP and runs on a virtual clock
with the committed cost curve as the service time. Under real HTTP the completion times are not
reproducible, so a bit-identical decision log is not expected there; this is stated in the test.

Behaviour summary, one frozen SYNTHETIC trace, 2 dashcams + 2 robots, 486 opportunities, 120 s
window, tight memory (`--gpu-kv-tokens 62944 --host-tier-gib 27`), mode A, seed 1, `--dry-run`.
All eight arms saw ONE opportunity stream (identical D96 `fairness_digest`
`4fb71a27a98c2576...`). **NOT A MEASUREMENT**; committed
as `results/orchestration/live2/coord/live2_coord_arm_legality.json` with
`is_measurement: false`.

| arm | requests | decisions | cloud answers | on time | decision latency p50 / p99 (ms) |
|---|---|---|---|---|---|
| policy-core (H = 1.0, mu = 0) | 452 | 452 | 446 | 446 | 7.68 / 13.17 |
| edf | 487 | 922 | 485 | 485 | 0.047 / 0.068 |
| edf-piece1024 | 489 | 924 | 485 | 485 | 0.047 / 0.067 |
| edf-piece2048 | 487 | 922 | 485 | 485 | 0.047 / 0.067 |
| utility-per-cost | 486 | 486 | 486 | 486 | 0.048 / 0.055 |
| always-cloud-fcfs | 486 | 486 | 486 | 486 | 0.043 / 0.048 |
| b9 | 476 | 476 | 476 | 476 | 0.088 / 0.102 |
| device-only | 0 | 6 | 0 | 0 | 0.042 / 0.057 |

The policy arm's decision latency is two orders of magnitude above the baselines' because it is
the only arm that rolls the engine forward; at this fleet size it is still well inside its own
H. `edf` logs about two decisions per request because pi_0 emits DEFER(0) for every pending item
it does not release this epoch, and every defer is logged. `edf-piece1024` sends two requests
more than `edf` because a 1,024-token piece does not cover this trace's small histories in one
go: the synthetic sessions reach only about 1.4k to 4k D2 tokens in 120 s, so the chain is two
to four pieces where the real 11k history is eleven (which the chaining test covers directly).

## 10. Scale smoke (test i)

64 devices (32 dashcam + 32 robot), 180 s window, tight memory
(`gpu_kv_tokens = 62,944`, `host_tier_gib = 27`), SYNTHETIC trace, the CPU stub, bodies sent
with uuid-only frame references (no image bytes). Mode A for `policy-core` and `edf`, mode B for
`policy-core`. **NOT A MEASUREMENT**: the stub is ONE FIFO server drawing committed service
times, so it saturates at this fleet size by construction and the queue it builds is the
fixture's, not an engine's. The figures that mean anything are the coordinator's own.

| cell | opportunities | requests | decisions | decision latency p50 / p99 / max (ms) | coordinator CPU | request rate (per s) | epoch overruns | virtual time reached | wall guard |
|---|---|---|---|---|---|---|---|---|---|
| `policy-core/modeA` (tick 1.00 s) | 5861 | 129 | 5889 | 354.9 / 773.8 / 3222.1 | 91.9 % | 0.31 | 911 | 90.6 of 195 s | HIT |
| `edf/modeA` (tick 0.05 s) | 11616 | 2391 | 11727 | 0.9 / 1.3 / 13.9 | 10.0 % | 9.38 | 0 | 194.9 of 195 s | no |
| `policy-core/modeB` (tick 1.00 s) | 5869 | 0 | 6406 | 325.1 / 710.8 / 2941.1 | 92.0 % | 0.00 | 911 | 90.7 of 195 s | HIT |

Committed as `results/orchestration/live2/coord/scale/scale_smoke.json` with
`is_measurement: false`, one `result.json` and one `header.json` per cell. The three JSONL
streams of each cell ran to 6 to 12 MB of CPU-stub fixture log, so only the first three lines of
each are kept (`*.jsonl.head`) beside a `*.jsonl.trimmed` note giving the original line count and
the command that regenerates them; nothing analytical depends on them. Seed 1, 180 s window plus a 15 s drain, so
the full virtual run is 195 s; a cell that cannot keep up with its own tick is stopped by a
420 s WALL GUARD and says so, with the virtual time it reached.

WHAT THESE NUMBERS SAY.

* `edf` keeps up completely at 64 devices: zero epoch overruns, the full 195 s of virtual time
  in 255 s of wall clock, 10 % of one core, a decision in about 0.9 ms, and 2,391 requests on
  the wire at 9.4 per second (which is the stub's own ceiling, not the arm's).
* `policy-core` does NOT keep up: a decision costs about 355 ms at p50 and 774 ms at p99 against
  its own H = 1.0 s tick, it saturates one core (92 %), it reaches only 90.6 s of virtual time
  in 420 s of wall clock, and it therefore serves 129 of 5,861 opportunities. Mode B is the same
  picture with 6 pulls and NOTHING served inside the guard: the pull adds a round trip to a loop
  that is already behind.
* This is the OPEN item spec v4 section 14 names, "bounding decision latency at large fleets",
  measured on a fixture for the first time. The cost is the release loop: an admission pass plus
  one DeltaJ rollout per pending item per epoch, each rollout deep-copying the fleet, invoked on
  every event (open issue 10a). It is NOT the budget (7.2 of 180 GPU-seconds spent) and NOT the
  stub, which the `edf` cell shows can absorb nine requests a second.
* So round 1 at 64 devices needs either a cheaper loop (coalescing events within a tick,
  capping the per-epoch release loop, or the closed-form fallback of spec 6.5, which is a
  conditional mechanism and OFF) or an acknowledgement that the coordinator's own latency enters
  the result at that fleet size. Both are decisions for the user, not for a build session, and
  the pilot (D95) is where they should be taken: its sizes are 4, 8, 16, 32, 64, so the break is
  measurable on the H100 before the main sweep.

The same three cells were run twice, once before and once after D96; the two agree on the
picture and differ in the detail a wall-clock-bounded cell always differs in (the pre-D96 pass
reached 117.9 s at p50 190 ms in mode A). The committed artifact is the post-D96 one, and
`fairness_digest` is in every cell's `result.json`.

## 11. Open issues

These are the things the parent session and the user need to see. The first one needs a USER
DECISION before D79 block 2 runs.

**1. H = 0.5 s silences monitoring admission by construction. USER DECISION NEEDED.**
Measured on the synthetic fixture, two dashcams and one robot, 60 s, mu = 0, everything else
equal and after the in-flight fix of issue 3:

| H | SH instants escalated | admitted | declined | DeltaJ of the declines | requests sent |
|---|---|---|---|---|---|
| 1.0 s | 240 | 240 | 0 | n/a | 242 |
| 0.5 s | 240 | 0 | 240 | exactly 0.0 for all 240, while Ghat was 0.056 to 0.080 | 2 |

Traced to the library, not to this harness. Spec 6.2's SH utility is credited only at
CADENCE-GRID POINTS inside the horizon: `policy/rollout.py::_opportunity_utility` walks
`o = t0, t0 + T_k, ...` while `o < t0 + H`, and an opportunity is served only by a delivery with
`delivered_at <= o`. With T_k = 0.5 s (D73 / StudyCTRL1-episodes) and H = 0.5 s the grid holds
exactly ONE point, `o = t0`, which no action taken at t0 can ever serve, so the marginal utility
of admitting a monitoring call is structurally zero. Spec 6.3's terminal value has no term for a
monitoring call still in flight at the horizon: it values unfinished RC jobs (continuation
value) and readiness (state value) only. Consequently the four policy versions at H = 0.5 s in
D79 block 2 would admit no monitoring at all, for a reason that has nothing to do with the
fleet, the load or mu. NOTHING WAS CHANGED IN THE LIBRARY. The options (sweep H over values
above one cadence; give a monitoring call in flight a terminal term; keep 0.5 s and report it as
a degenerate cell) are a design decision for the user.

THIS IS URGENT RATHER THAN MERELY OPEN, because D95 part 4 fixes the PILOT's policy version at
mu = EWMA and **H = 0.5 s**. On this evidence that pilot would serve no monitoring instant at
all, and its break sizes would describe a policy that declines every SH opportunity by
construction. The pilot is also where D88's x0.5 and x2 fixed mu values are fixed, so the
setting propagates. Taking the decision before the pilot runs costs nothing; taking it after
costs the pilot.

**2. The EWMA mu estimator needs its input fed by the caller, and now is.**
`Coordinator._update_mu` reads `self._last_delta_j`, which is assigned NOWHERE in
`experiments/orchestration/policy/`; the library's own tests set it from outside
(`policy/tests/test_pol3_update.py:325`, `:334`). Left unset it is 0 through `getattr`, so the
EWMA arm would be bit-identical to mu = 0 and D88's two fixed values, which are x0.5 and x2 of
its time average, would both be 0. The policy arm therefore sets `co._last_delta_j` from the
DeltaJ of the last released item at the end of each epoch (used by the next epoch's update: a
one-epoch lag, which is what "the last released item" means). Nothing in `policy/` was modified.
On the synthetic fixture the EWMA now moves (mu reaches about 0.76 within 40 s, time average
1.053); that number is a fixture artifact and D88's fixed values must come from the PILOT.

**3. A released item never left the policy's in-flight set, which silenced admission. FIXED.**
Found during the build: the coordinator released items into `fleet.in_flight` and nothing ever
removed them, so the rollout saw an engine that never emptied, every new candidate's predicted
start fell beyond the horizon, and SH admission returned DeltaJ = 0 for reasons unrelated to the
fleet (9 of 120 instants admitted instead of 120 of 120). Fixed in the harness two ways: the
coordinator now calls `arm.live2_completed(...)` when a request finishes, and the policy arm
also drops in-flight items whose deadline has passed as a safety net. This is an IMPLEMENTATION
FIX in live2, not a change to the library, and it is reported because every number taken before
it is wrong.

**3b. The piece-chaining arms built only their first piece. FIXED.** Two coupled defects, both
found by inspection after the behaviour table showed `edf`, `edf-piece1024` and `edf-piece2048`
producing identical request counts: (i) `Pi0Edf` issued MATERIALIZE once per session, which
under the one-piece-per-action semantics builds a single piece and leaves the chain unfinished;
(ii) the coordinator marked a session GPU-warm after the FIRST piece completed, so a chaining
arm then saw GPU-WARM and stopped. Fixed: the arm issues MATERIALIZE while the history is
unbuilt (the coordinator no-ops once it is complete), and the believed tier becomes `gpu` only
when `built_tokens >= est_tokens`. A new test drives the chain at StudyENG1's realistic
11,184-token D2 history and asserts 11 pieces of at most 1,024 tokens summing to 11,184, that
`slice_tokens = None` is one request, and that later pieces carry uuid REFERENCES for the
already sent frames rather than re-sending their bytes. The synthetic trace's own sessions are
too short to reach that size, which is why the defect survived the end-to-end runs, and why the
chaining check is a unit test on the real history size.

A related limitation, not a defect: `readiness` has no partial value, so while a rebuild is
incomplete the arm sees COLD even though the built prefix is reused on the wire as uuid
references and the request is therefore cheap. The cost model consequently OVERSTATES the work
of a later piece. Fixing it properly means adding a partial readiness to a committed interface,
which a build session may not do.

**4. The pending set is pruned, on spec 7.9's authority.** A held monitoring call still unsent
when its own window has passed IS a device-only outcome (D24, spec 7.9, merging OFF and its
enabling condition not met), so it leaves the pending set instead of competing forever.
Without it the pending set grows with the run and the release loop's cost grows with it, which
is the OPEN item spec section 14 names. Reported so the user can object.

**5. The library opens an Episode per admitted SH instant.** `Coordinator.escalate` creates an
`Episode` (spec 7.1, from D19) for every admitted SH request. Under D62 monitoring is PER
INSTANT, so the coordinator treats an admitted instant as one call and never dispatches episode
follow-ups; the Episode objects are inert bookkeeping and are pruned after H_s so the fleet the
rollout deep-copies does not grow with the run. D19's own note already records that its SH part
is revised by D62; the library and the manuscript still need reconciling.

**6. MATERIALIZE enactment: one action advances the build by ONE piece.** StudyLIVE1's adapter
issued a whole prefix chain on one MATERIALIZE; live2 advances one piece per MATERIALIZE, so
each piece is a separate decision and a separate request an arm can hold or re-order, which is
the point of the per-piece port. `slice_tokens = None` builds the remainder in one request (the
monolithic option every pre-amendment baseline can express). The rule is identical for every
arm, so no arm gains or loses by it, but it IS a semantic choice in a new harness and is flagged
here rather than buried.

**7. The digest question is CLOSED by D96.** The canonical fairness digest is now the fleet's
order-independent 64-hex sha256, reproduced field for field here and asserted byte-identical to
`fleet/trace.py::fairness_digest` in both modes. `adapter.trace_digest` itself is still not
literally reusable, because it takes a StudyLIVE1 trace OBJECT (`.mix`, `.fleet`, `.sessions`,
`.streams`) and live2's trace is an event stream; its rule survives only as
`live1_trace_digest`, which no header presents as the fairness digest.

**8. The harness budget is an artifact that needs a decision.** `interface.Budget` is set to
`window_s x 1.0` GPU-seconds, identical for every arm, as StudyLIVE1's adapter does. Round 1 has
no fixed budget (D58: "budget %" is only a test variable), but B8, B9 and `edf-service-time`
admit by a utility-per-GPU-second ratio against a remaining budget and need a finite one. The
value is currently a harness constant; it should become an explicit input like the capacities,
or be set from the round-1 load, before any measured run.

**9. The interface carries no per-instant monitoring deadline.** `EpisodicStream` has no
deadline field, so arm 4's pi_0 orders monitoring calls by the deadline it CAN observe: the next
call due after the last answer the application received, plus the monitoring bound. Without that
every stream would tie on `now + L` and pi_0's tie-break by item_id would starve every device
but the first (observed: one of two dashcams served 240 instants and the other none). An
alternative is to add a per-instant deadline to the observation, which changes a committed
interface and was therefore not done.

**10. The policy arm receives a roster hook outside the scrubbed observation.**
`interface.RecallQuery` carries `session_id` but not `device_id`, and per-device deficit
counters plus D82's POOLED robot target need the device. `arm.live2_roster(...)` carries only
the device roster (id, type, uplink, RTT), the session-to-device ownership and the per-device
frame byte size: facts every arm could know, with no future and no per-opportunity information.
The observation itself still goes through `scrub`, and the registry arms do not model devices at
all, so nothing is withheld from them that they could use.

**10a. "On each event and on a tick" makes the policy arm run about 20 times per second at 64
devices.** The brief's rule is that the arm is called on EVERY event and on its own tick. At 64
devices an event (an instant, a frame, a batch, a question) lands in nearly every 50 ms grid
step, so the H = 1 s arm is in fact invoked about 20 times per virtual second, each invocation
carrying an admission pass plus a release loop of rollouts. That is why the scale cell is
dominated by decision cost. If the user wants a cheaper loop the knob is to COALESCE events
inside a tick for arms that have one (decide once per H, with the events of that interval
batched), which is a scheduling change to the harness and so a decision rather than something a
build session should take.

**11. What the CPU stub cannot test.** It reports no `prompt_tokens_details.cached_tokens`, so
D81's WARM / COLD tag is `None` on every stub request (never 0, which would be a fabricated
cold path), and the warm / cold accuracy split cannot be exercised on flash. The real-engine
cache-isolation check is written out as a procedure in section 3 and is an H100 task. The stub
is also ONE FIFO server, so it saturates at 64 devices and no latency or capacity number from it
means anything.

**12b. The live wiring is through the EMULATOR, and the bridge for it is now written.** The
fleet emulator owns the clock for a live run and calls a coordinator through its own Protocol
(`fleet/emulator.py:76-78`: `on_event(event, t)`, `tick(t)`, both returning replies), while
`Live2Coordinator.run()` owns its clock and consumes a static event list. `live2/bridge.py`
exposes the coordinator through that Protocol, carrying the emulator's `t` on every call so the
bridge keeps no clock of its own, and returning the `pull_request` and `cloud_answer` events
produced since the last call. Three tests cover it: the Protocol is satisfied and cloud answers
come back on-schema, pull mode replies with `pull_request`, and an off-schema event is refused
at the bridge. What is NOT yet tested is the real `FleetEmulator` driving it, because that needs
a trace directory with the committed frames and answers, which are not on this box. Note also
that the fleet's `trace.jsonl` holds the fleet's INTERNAL record shape (`monitor_opportunity`,
`history_batch`, a single `t`), not the wire schema: the emulator is the converter, so a live
run goes trace records -> emulator -> wire events -> bridge -> coordinator, and
`traces.load()` is for replaying a WIRE-event JSONL, not for reading `trace.jsonl` directly.

**12a. Integration with the fleet's own trace is wired but UNTESTED end to end.**
`traces.load` accepts both shapes of a WIRE-event JSONL: a file whose first record is a
`_header`, and one with a sibling `trace_meta.json` (`fleet/trace.py::write_trace`), from which
it takes the seed and the mode; such a trace is labelled FLEET and is allowed against a real
server. It is NOT a reader for the fleet's internal record shape, which goes through the
emulator (see 12b). Every record is parsed through `schema.parse`, so an
off-schema trace fails at load. At the time of this build no `trace.jsonl` was committed (only
`trace_meta.json` under `results/orchestration/live2/fleet/`), so the only end-to-end runs were
on SYNTHETIC traces. The parent should run one cell per arm on a fleet trace before the pilot,
and check that `traces.fairness_digest` and the fleet's own `fairness_digest` agree on it, which
the byte-equality test guarantees only for the synthetic stream so far.

**12. Dependencies on subagent B and on pending H100 work.** The coordinator reads JPEG frames
from the `frame_ref` paths the fleet supplies; B's encoder and its sha256 manifest (D70, D91)
are the producers, and until they exist the tests use placeholder bytes and the coordinator
REFUSES a SYNTHETIC trace against a real server. A measured run additionally needs the dense
JPEG refit of both calibration maps (D86): the coordinator refuses an INTERIM map against a real
server, and the committed `orin2_calibration.json` is INTERIM. Mode B currently uses
`traces.pull_responder` to emulate the device's reply to a pull (charging RTT / 2 plus the
upload); when B's fleet process is wired in, the responder must be replaced by the real fleet
and the pulled path's delivered delay re-checked. Task value (streaming AP, recall accuracy,
D85) is scored offline by B's scorer; `device-only` sends nothing and must be scored entirely
from the recordings (D87).

**13. The 0.567 s device-answer charge is implemented and unexercised.** No arm among the eight
declares `reads_device_answer`, so D87's StudyD8 rule never fires. It is wired both as a
visibility delay and as the delivery time of a DEVICE outcome, so an arm that does declare it is
charged automatically.

**14. `--cost-model` accepts the frozen model's variants only.** `pol4` (default, frozen),
`eng1` and `pol4_nobatch`, which is `eng1_engine.ENGINE_MODELS`. pol6 lives in its own module
and did not pass its one-shot before this build, so per D74 round 1 uses pol4. If pol6 passes
before round 1 starts, adding it means extending `ENGINE_MODELS` or passing a pol6 engine
object, which is a change to `policy/` and so a stop condition for a build session.


## 11b. What D95 (the pilot design) needs from this harness

D95 was committed during this build. Against it, the harness is ready except for the two items
already named above:

| D95 item | state here |
|---|---|
| 600 s runs, same as main | `--window-s 600`; nothing in the loop is tied to 180 s |
| sizes 4, 8, 16, 32, 64, doubling further | `--n-dashcam` / `--n-robot`, or a fleet trace; section 10 shows 64 is where the POLICY's own decision latency binds, so the harness limit D95 refers to is the coordinator, not the emulator |
| arms: policy and EDF at every size, then always-cloud FCFS and EDF + 1,024 pieces | all four are arms 1, 4, 3 and 5, selectable by `--arm` |
| policy version mu = EWMA, H = 0.5 s | both selectable (`--mu-mode ewma --h 0.5`), and every EWMA run logs `mu_time_average`, which is what D88 reads. **But H = 0.5 s is open issue 1** |
| roomy check at 256 GiB | `--host-tier-gib 256`; the conversion to tokens is explicit in `run_live2_cell.py` |
| pilot seed 0, never used in a reported run | `--seed 0`; the seed is in the run header and in the cache salts, so a pilot run can never be confused with a reported one |
| pilot report: break sizes, minutes per run, coordinator decision latency, cache-isolation result, a predicted-vs-actual sample, any INVALID runs | the per-cell `result.json` carries decision latency, CPU, wall time, request rate, overruns and the wall guard; `predicted_vs_actual.json` carries the D63 sample; the cache-isolation check is the H100 procedure in section 3 |
| prerequisites in order: JPEG encode and store, dense calibration refit, cross-device cache-isolation check | all three are enforced as REFUSALS rather than left to discipline: a SYNTHETIC trace and an INTERIM map are both refused against a real server, and frames are read from the paths the fleet supplies |

## 12. Mechanism verification and results consistency

This row is an ENGINEERING TASK with NO MEASUREMENT, so neither protocol is run on it, and that
is a statement about this row only:

* **Mechanism verification** (CLAUDE.md) applies to an experiment that tests a causal claim
  before its sweep runs. This build tests no causal claim; it produces no sweep and no finding.
  The protocol belongs to the round-1 measured runs, where the causal chain is D64's (joint
  representation x placement x timing beats decomposed policies under a quality SLO) and the
  instantiating quantities are the ones this coordinator now logs per decision and per request.
* **Results consistency check** applies to an experiment that produces numbers. Every number in
  this report is a CPU-stub or dry-run fixture output, labelled as such in its own
  `result.json` (`is_measurement: false`) and in every run header. None of them is committed as
  a measurement of any quantity, so there is nothing to cross-check against
  `results/INDEX.md`. The committed values this build READS (StudyD8's 0.567 s, the StudyRH4 D2
  token arithmetic, the StudyE10a byte medians, StudyORIN2's calibration a / b, the StudyENG1
  step model through pol4, the D76 capacities) are read through the existing loaders and are
  not recomputed here.

Per the standing rules, `research/EXPERIMENTS.md`, `research/STATUS.md` and `results/INDEX.md`
were NOT edited by this session; the parent session owns those rows.

## 13. Files created or changed

CREATED (all new):

```
experiments/orchestration/live2/schema.py
experiments/orchestration/live2/CONTRACT.md
experiments/orchestration/live2/cachekeys.py
experiments/orchestration/live2/bodies.py
experiments/orchestration/live2/backend.py
experiments/orchestration/live2/calib.py
experiments/orchestration/live2/cstate.py
experiments/orchestration/live2/arms.py
experiments/orchestration/live2/arms_policy.py
experiments/orchestration/live2/coordinator.py
experiments/orchestration/live2/traces.py
experiments/orchestration/live2/bridge.py
experiments/orchestration/live2/joiner.py
experiments/orchestration/live2/run_live2_cell.py
experiments/orchestration/live2/scale_smoke.py
experiments/orchestration/live2/tests/test_live2_coord.py
experiments/orchestration/live2/tests/test_live2_fakeserver.py
reports/study_live2_coord.md
results/orchestration/live2/coord/live2_coord_arm_legality.json
results/orchestration/live2/coord/scale/scale_smoke.json
results/orchestration/live2/coord/scale/{policy-core_modeA,edf_modeA,policy-core_modeB}/
    result.json, header.json, calibration_knots.json (policy cells),
    *.jsonl.head and *.jsonl.trimmed
```

CHANGED: nothing. No tracked file was modified by this session. In particular
`experiments/orchestration/policy/*`, `baselines/constructed.py`, `baselines/interface.py`,
`baselines/registry.yaml`, `baselines/naive.py`, the frozen pol4 cost model, the existing
`experiments/orchestration/live/*` harness and every earlier result are untouched;
`research/EXPERIMENTS.md`, `research/STATUS.md` and `results/INDEX.md` belong to the parent
session, and `live2/fleet/`, `live2/scorer/` and `live2/data/` belong to StudyLIVE2-fleet.
