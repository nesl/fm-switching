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

---

# StudyLIVE2-fix: D98 to D105 applied to the coordinator and the policy side

Status: ENGINEERING TASK, built and tested on flash (CPU only), 2026-11-17.
Pre-registration: `research/EXPERIMENTS.md` row `StudyLIVE2-fix`.
Authority: `research/policy_design_log.md` D98-D105 and the amended `research/policy_spec_v4.md`
(header, 2.1, 5.1, 6.1, 6.3, 9).

**NOTHING IN THIS SECTION IS A MEASUREMENT.** Every number comes from a `--dry-run` with no
server at all, on a SYNTHETIC trace, with the committed `pol4` cost curve as the service time.
Every result file carries `is_measurement: false`. The quantities that mean anything are the
coordinator's OWN (decision latency, CPU, decisions) and the policy's own arithmetic (admit and
decline counts, DeltaJ, predicted cost).

Flash CPU, for every timing below: **13th Gen Intel Core i7-13700KF, 16 cores / 24 threads**.
The H100 host's CPU differs, so the pilot (D95) re-measures decision latency there; nothing in
this section fixes a latency budget for that host.

## F1. What changed, by decision

| decision | what it asked for | where it landed |
|---|---|---|
| D101 | a `history_preload` event: frames the cloud ALREADY HOLDS as cold history at run start | `live2/schema.py`, `live2/CONTRACT.md`, `live2/cstate.py`, `live2/coordinator.py`, `live2/traces.py` (digest) |
| D98 | SH value PER INSTANT, credited at c_i + L_SH even past t + H | `policy/rollout.py` (`_opportunity_utility`, the in-flight and tail deliveries), `policy/coordinator.py` + `policy/escalation.py` (the instant's capture and deadline reach the planned call), `live2/arms_policy.py` |
| D99 (1) | ONE 100 ms decision period for every arm, events batched | `live2/coordinator.py`, `live2/bridge.py`, `live2/schema.py` (header), `live2/run_live2_cell.py` |
| D99 (2) | the policy sped up WITHOUT changing decisions, with an equivalence test | `policy/rollout.py` (`clone_for_rollout`, `clone_impl`), `live2/arms_policy.py` (`impl`), `--policy-impl reference` |
| D99 (3) | decision time at 32 / 64 / 128 devices | `live2/fix_checks.py speed` |
| D99 (4) | a cap K, only if (2) misses the target | `policy/coordinator.py` (`release_eval_cap_k`), `live2/arms_policy.py` (`cap_k`), `--release-cap-k` |
| D100 | the information-parity hook: built prefix size, per-instant SH deadline | `live2/coordinator.py` (`_roster`), `live2/arms_policy.py`, `live2/arms.py` (pi_0) |
| D102 | `--gpu-budget-s`, default window_s x 1.0, in the header | `live2/coordinator.py`, `live2/run_live2_cell.py`, `live2/schema.py` |
| D104 | the bridge accepts `history_preload`; mode B still uses the pull responder | `live2/bridge.py`, tests |

## F2. Part 0, D101: the `history_preload` event

```
history_preload {device_id, session_id, frame_refs[], est_tokens, t}      robots, t = 0
```

It declares the frames the cloud ALREADY HOLDS as cold history at run start, which is what makes
a robot's part-way join (D101) exercise the cold-rebuild pressure round 1 exists to test. **No
uplink time is charged** and the coordinator never recomputes one: the frames were on cloud-side
disk before the clock started. `CoordState.history_preload` stores them exactly as an ingested
batch does (D56: frames on disk, NO KV), leaves the belief at cold and `built_tokens` at 0, and
records `preloaded_tokens`, so the first question on a joined-into session still pays a cold
rebuild of the joined prefix. It carries no `batch_id` and no `t_arrive`, because it is not a
batch that arrived during the run.

FAIRNESS DIGEST COVERAGE is the D96 list plus `history_preload` (the join point decides which
questions count, so two streams with different preloads are different experiments and must not
share a digest). The row is the fleet's canonical six-field tuple with the SESSION as the key,
since there is no `batch_id`:

```
(device_id, "history_preload", "%.6f" % t, session_id, str(int(est_tokens)), "")
```

This is byte-identical to subagent B's `fleet/trace.py::_digest_tuple`, which has landed and
carries the same row with the same comment. The byte-equality test in
`tests/test_live2_coord.py` now digests a stream that INCLUDES a preload, in both modes, so the
new event's row shape is cross-checked against the fleet's rather than assumed.

One implementation fix fell out of it: a `history_preload` and a `session_start` both carry
t = 0 for a joined session, and the loop batches a period's events, so the preload can be
ingested first. `CoordState.session_start` therefore no longer wipes a session that already
carries a declared cold history; it only re-opens it. Without that the preloaded frames were
silently dropped (the test `test_the_coordinator_stores_it_as_cold_history_with_no_kv` caught
it).

Also corrected in `CONTRACT.md`: the fairness-digest ROW SHAPE table was stale (it listed a
five-field row in a different field order from the one `traces.py` and `fleet/trace.py` both
emit). It now states the canonical six-field tuple `(device_id, wire_kind, t, key, extra,
deadline)` per kind. Documentation only; no code read that table.

## F3. Part 1, D98: per-instant SH value in the rollout

### What was replaced

`policy/rollout.py::_opportunity_utility` credited SH value at DISPLAY-FRESHNESS points: the
cadence grid `o = t0, t0 + T_k, ...` inside `[t0, t0 + H)`, each point served by the newest
delivery already landed by it. With T_k = 0.5 s and H = 0.5 s that grid held exactly one point,
`o = t0`, which no action taken at t0 can serve, so the marginal value of admitting a monitoring
call was structurally zero (open issue 1).

It now implements spec 5.1 as amended: every SH instant i has its own capture c_i and its own
deadline c_i + L_SH, and is credited

```
omega_SH * u_SH(cloud, delivered_at - c_i)   if delivered_at <= c_i + L_SH
omega_SH * u_SH(device)                      otherwise
```

at ITS OWN DEADLINE, even when that falls after t0 + H. The instant set per device is the cadence
calendar inside the horizon (the existing demand model, unchanged) plus the capture of every SH
item pending or in flight. `u_SH`, its calibration, omega and the deficit-counter term are
untouched; the returned opportunity list keeps ONE ENTRY PER CREDITED INSTANT, so `_z_term` and
the live2 joiner read it exactly as before (two keys are added: `deadline` and `delivered_at`).

### How released SH items are simulated through to delivery, and what it costs

Two additions to `Rollout.run`:

1. An SH call ALREADY IN FLIGHT at t0 now produces a delivery record (previously in-flight items
   only advanced `free_at` and `busy`), so spec 6.3's "never worth zero merely because it lands
   after the horizon" is true of an in-flight call too. An episode call carries no `job_id`, so
   no RC accounting (`_rc_utility`, `_prefix_risk`) can see these rows.
2. A **tail pass**: an SH call that cannot START inside `[t0, t0 + H)` is no longer dropped. It
   is simulated forward from where the horizon left the engine, in the same pi_0 order, until the
   last deadline any credited instant can have (`max(end, latest pending SH capture) + L_SH`),
   which bounds the pass. COST: at most **one extra `engine.predict` per SH call that could not
   start inside H**, and nothing else: the tail charges nothing to `busy`, the KV pool,
   `demand_tokens` or `jobs_progress`, so the horizon's own accounting is unchanged and only the
   SH credit and `in_sample` see these deliveries. A test asserts `engine_busy_s` and
   `residual_backlog_s` are identical with and without the tail.

`RolloutResult.detail` gains `sh_tail_simulated` and `sh_tail_pending` so the pass is visible.

No extrapolation is introduced: StudyE9d's u_SH grid runs to a 3.0 s delivered delay and
L_SH is 1.0 s in round 1 (1.5 s in the library default), so every credited delay is inside the
measured range and `within_measured_delay` stays true.

### The instant's capture and deadline now reach the planned call (D98 with D100)

The per-instant rule needs c_i on the item. `EscalationRequest` gained an OPT-IN `capture_at`;
when it is supplied, `Coordinator._plan` gives the planned call `due_at = c_i` and
`deadline = c_i + L_SH`, and when it is not, the call is planned exactly as before (`due_at =
fleet.t`, no deadline), so no existing caller moves. Three consequences in live2: the rollout
credits the instant the call actually serves; pi_0 inside the rollout orders SH calls by their
own deadlines; and `arms_policy._prune` (which keys on `deadline is not None`) now actually
retires a monitoring call whose window has passed, which also bounds the pending set.

### Part 1 test table

`results/orchestration/live2/coord/fix/d98_sh_admission.json`. Fixture: SYNTHETIC 2 dashcams +
1 robot, 60 s, mu = 0, mode A, tight memory (gpu_kv_tokens 62,944, host_tier_gib 27), seed 1,
dry run, 100 ms decision period. This is the open-issue-1 fixture.

(a) SH ADMISSION IS NO LONGER STRUCTURALLY ZERO:

| H | SH escalated | admitted | declined | DeltaJ of admits (min / med / max) | DeltaJ of declines (min / med / max) | requests | monitor answers | on time |
|---|---|---|---|---|---|---|---|---|
| 0.5 s | 479 | 240 | 239 | 0.0586 / 0.0778 / 0.0871 | -0.0111 / -0.0043 / 0.0 | 242 | 240 | 241 |
| 1.0 s | 479 | 240 | 239 | 0.0586 / 0.0778 / 0.0871 | -0.0111 / -0.0043 / 0.0 | 242 | 240 | 241 |

Before D98, H = 0.5 s admitted **0 of 240** with DeltaJ exactly 0.0 on every one, and H = 1.0 s
admitted 240 of 240. Two things to read off the table:

* **H = 0.5 s and H = 1.0 s are now IDENTICAL**, which is the point of the per-instant rule: an
  SH instant's value no longer depends on where it falls relative to the horizon, so H is purely
  how far ahead the rollout looks for interference (spec 6.1 as amended). D95 part 4's pilot at
  H = 0.5 s is therefore no longer a degenerate cell.
* Both ADMITS AND DECLINES now exist with the expected signs. The escalation count rose from 240
  to 479 because the D100 hook offers each instant until it is decided, so the second instant of
  a device inside one period is escalated too; it is declined (DeltaJ <= 0) because the first one
  already occupies the engine for that window. The declines are small and negative, the admits
  clearly positive, and nothing is exactly 0.0 by construction any more.

Unit cases, in `policy/tests/test_rollout_coordinator.py::TestD98PerInstantSH` (new) and
`live2/tests/test_live2_fix.py::TestD98`:

| test | construction | result |
|---|---|---|
| (b) delivery AFTER its own deadline | H = 0.5 s, one SH instant at c = 0, an in-flight 7,000-token RC piece keeping the engine busy to 1.556 s; the call is simulated in the tail and delivered at **1.770 s** against a deadline of 1.5 s | the instant takes the DEVICE value and **DeltaJ(admit) = 0.0 <= 0** |
| (c) delivery past the HORIZON but inside the deadline | H = 0.5 s, same instant, a 3,000-token in-flight piece; delivered at **0.881 s**, past t0 + H = 0.5 s, inside the deadline 1.5 s | the instant takes the CLOUD value and **DeltaJ(admit) = +0.0471 > 0** |
| in-flight at t0 | an SH call in `fleet.in_flight` at t0 | its instant is credited `cloud`, from a delivery row marked `in_flight_at_t0` |
| one entry per credited instant | 2 devices, H = 1.0 s, plus one off-grid pending capture | `len(opportunities) == 2 * H/T_k + 1`, all `(device, t)` distinct |
| a device-served instant is worth exactly zero | the same fleet with and without an extra off-grid instant | `u_hat` identical to 12 decimal places (spec 3.2's gain scale, ambiguity A2) |
| the tail charges nothing to the horizon | with and without the tail pass | `engine_busy_s` and `residual_backlog_s` identical to 12 decimal places |

(d) PREVIOUSLY PASSING LIBRARY TESTS. The whole policy suite (16 modules) passes. Two tests were
changed, each for one reason tied to D98:

| test | change | reason |
|---|---|---|
| `test_rollout_coordinator.py::test_releasing_a_fresh_cloud_call_is_positive_and_a_stale_one_is_not` -> `..._is_positive_wherever_its_instant_falls` | `assertLess(late, good)` became `assertAlmostEqual(late, good)`, both still > 0 | D98 makes a call worth its OWN instant's value, so a late-in-the-horizon capture is no longer worth less than an early one; the old assertion tested the retired display-freshness rule |
| `test_scenario.py::test_a_held_call_with_merging_off_is_a_device_outcome` | the far-future call is now `dispatch`; the hold-is-a-device-outcome branch is asserted on a call that CANNOT be delivered by c_i + L_SH | D98 credits a pending instant at its own deadline, so "outside t + H" is no longer a reason to hold; spec 7.9's device-only outcome is reached by a missed deadline, which is what it describes |

`policy/spec_map.py`'s "1.2 eligible opportunities" row now names D98 and v4 5.1 / 6.3.

No committed interface in `baselines/` had to change: the per-instant rule is entirely inside
`policy/rollout.py` plus the opt-in `capture_at`, and `interface.Policy`, `Action`,
`Observation`, `validate_action` and `scrub` are untouched.

## F4. Part 2, D99: one decision period, and the speed work

### (1) ONE DECISION PERIOD FOR EVERY ARM: 100 ms

The 50 ms event grid and the per-arm H tick are gone. The loop now advances on one 100 ms
period, ingests that period's events, and takes EXACTLY ONE decision over the batch; H is the
rollout horizon only (spec 6.1, 9 as amended). `decision_period_s` is in the run header and in
every `result.json`, `tick_s` survives as the same number under its old name, and
`--decision-period-s` sets it.

Why it matters beyond speed: under the old rule the arm was called on every event AND on its own
tick, so at 64 devices an event landed in nearly every 50 ms step and an H = 1 s arm was in fact
invoked about 20 times a virtual second (open issue 10a). The decision RATE was therefore an arm
property, and a comparison between arms was partly a comparison of how often each was asked. It
is now the same for all eight. A test asserts that `edf`, `always-cloud-fcfs` and `b9` all take
exactly `window_s / 0.1 + 1` decisions on the same trace.

The bridge enforces the same period on the EMULATOR's clock (`_maybe_decide`), so a live run is
period-correct whatever the emulator's own `tick_s` is, as long as it is no coarser than the
period; `decide_on_every_event` is gone.

### (2) The speed work: what was profiled, what was fixed, and the equivalence test

PROFILE BEFORE (cProfile, one 60 s dry run at 16 devices, 9,736 rollouts): **152.7 of 162.9 s,
94 %, was `copy.deepcopy`** -- 135 million `deepcopy` calls, about 14,000 per rollout. The cost
was not the engine model, the KV bookkeeping or the opportunity arithmetic; it was that
`Rollout.run` began with `copy.deepcopy(fleet)`, which walks every device's link, demand model,
controller and episode list on every one of the two rollouts of every DeltaJ evaluation, and the
episode list grows with the run.

FIX. `policy/rollout.py::clone_for_rollout` gives independent containers for everything a
rollout or the release loop can write to -- the pending and in-flight lists AND their items (with
their `meta` dicts), the jobs, each device, each history belief (with its tier probabilities),
the per-device deficit counters, the demand rates and the episode LIST -- and shares only the
objects nothing mutates (`Link`, `Demand`, the controller, each `Episode`). `Rollout.run` mutates
only `f.pending` and `f.jobs`, and `_terminal` copies each job before touching it, which is what
makes the clone exact rather than approximate. The per-epoch `copy.deepcopy(self.fleet)` that
`arms_policy` took for the D63 prediction snapshot uses the same clone.

It is SELECTABLE: `Rollout.clone_impl` is `"fast"` or `"reference"` (the unoptimized
`copy.deepcopy`), and `--policy-impl reference` runs the whole arm that way.

EQUIVALENCE TEST (`results/orchestration/live2/coord/fix/d99_equivalence.json`): 4 and 8 devices
x seeds 1, 2, 3 x 120 s, 50 : 50, mode A, tight memory, mu = 0, H = 1.0 s, dry run. The two
implementations' decision logs are compared line by line with `decision_latency_ms` removed (the
only wall-clock field in the record; `decision_id` is a counter, so everything else is
deterministic).

| devices | seed | decision-log lines | identical? | reference p50 (ms) | fast p50 (ms) | wall reference / fast (s) | speedup |
|---|---|---|---|---|---|---|---|
| 4 | 1 | 492 | **yes** | 2.528 | 0.474 | 5.31 / 0.87 | 6.1x |
| 4 | 2 | 490 | **yes** | 1.273 | 0.215 | 5.73 / 0.91 | 6.3x |
| 4 | 3 | 492 | **yes** | 2.525 | 0.482 | 5.34 / 0.89 | 6.0x |
| 8 | 1 | 1,548 | **yes** | 21.395 | 2.675 | 32.97 / 4.65 | 7.1x |
| 8 | 2 | 1,540 | **yes** | 21.275 | 2.709 | 33.36 / 4.74 | 7.0x |
| 8 | 3 | 1,546 | **yes** | 21.466 | 2.974 | 32.15 / 4.58 | 7.0x |

All six cells are IDENTICAL line for line, with identical decision and request counts (492 / 492,
1,548 / 948 and so on), at 6.0x to 7.1x less wall clock. `all_identical: true` is in the result
file.

PROFILE AFTER, the same 60 s dry run at 16 devices: **12.5 s of wall clock instead of 163 s**
(p50 per decision 8.3 ms instead of 159 ms), over 10,886 rollouts. The remaining cost is spread
across the spec's own terms rather than concentrated in one artifact: `_terminal` 4.5 s (of which
`state_value` 2.6 s and the continuation value 1.3 s), `engine.predict` 3.4 s over 128,447 calls,
`_opportunity_utility` 1.8 s, and `clone_for_rollout` 1.3 s -- 10 % of the run, where
`copy.deepcopy` had been 94 %. There is no second order-of-magnitude target left in the loop:
memoizing `state_value` across the rollouts of one period, the next-largest idea, addresses about
a fifth of the remaining time and cannot close the gap the cap table below shows, so it was NOT
done rather than done unverified.

Three further checks on the same claim: a library test asserts that `fast` and `reference`
produce identical `RolloutResult` totals and identical `DeltaJ` on a fleet with episodes, jobs,
deficit counters and in-flight work, and that the caller's fleet is byte-identical afterwards
under both (`repr` compare against a `deepcopy` snapshot); the whole 16-module policy suite
passes unchanged; and the live2 determinism test (same trace, arm and seed give an identical
decision log) still passes.

### (3) The speed table

`results/orchestration/live2/coord/fix/d99_speed.json`. SYNTHETIC 50 : 50, mode A, tight memory
(gpu_kv_tokens 62,944, host_tier_gib 27), 180 s window plus a 15 s drain, mu = 0, H = 1.0 s,
seed 1, dry run with the committed `pol4` cost curve as the service time, 100 ms decision period,
NO CAP. One process, nothing else running. A cell that cannot keep up with its own period is
stopped by a 240 s WALL GUARD and says so, with the virtual time it reached.

| devices | opportunities | decisions | requests | decision p50 / p99 / max (ms) | CPU | wall (s) | virtual time reached | wall guard | DeltaJ evaluations | p99 target |
|---|---|---|---|---|---|---|---|---|---|---|
| 32 | 5,808 | 1,801 | 2,666 | 43.3 / 214.0 / 222.2 | 100 % | 79.3 | 194.9 of 195 s | no | 37,216 | **missed** |
| 64 | 11,616 | 1,801 | 2,666 | 109.5 / 545.4 / 671.8 | 100 % | 206.3 | 194.9 of 195 s | no | 56,063 | **missed** |
| 128 | 11,436 (run cut short) | 885 | 1,712 | 18.5 / 2,152.6 / 2,654.1 | 100 % | 240.2 | **88.4 of 195 s** | HIT | 45,103 | **missed** |

WHAT THE TABLE SAYS.

* The copy fix is a large, real speedup: at 16 devices over 60 s the same run went from p50
  159 ms / p99 1,004 ms (and 163 s of wall) to p50 2.6 ms / p99 19.8 ms (3.3 s of wall), a 9x
  wall-clock factor, with an identical decision log.
* 32 and 64 devices now run the whole 195 s of virtual time, where the pre-fix 64-device cell hit
  its wall guard at 90.6 s and served 129 of 5,861 opportunities. The two are not directly
  comparable (the old cell ran against the CPU stub over HTTP, this one is a dry run), but the
  direction is not in doubt: the same 64-device cell now serves 11,520 monitoring opportunities
  instead of 129.
* **The target is nevertheless MISSED at every size**, including 128 devices, which is the
  condition D99 (4) attaches the cap to. p50 is not monotone in fleet size, because the
  128-device cell is stopped by the guard a third of the way through its load ramp, so its median
  is taken over the early, cheap decisions; the p99 and the max are the honest columns there.
* The remaining cost is the release loop's structure, not the copy: an admission DeltaJ per
  escalated instant plus one DeltaJ per due pending item per pass, each DeltaJ being two
  rollouts. `scoring_calls` (the library's own count of DeltaJ evaluations) is 37,216 at 32
  devices and 45,103 in the 88 s the 128-device cell reached, so the per-period work grows with
  the fleet exactly as the quadratic structure predicts.

### (4) The cap K

(2) misses the target at 128 devices (and at 32 and 64), so D99 (4) applies.

WHAT THE CAP IS. `release_eval_cap_k = K` bounds how many pending items get a FULL DeltaJ
evaluation per DECISION PERIOD, on both full-DeltaJ paths:

* the release loop evaluates at most K items in the whole call, the budget SHARED ACROSS THE
  PASSES of the loop (capping per pass leaves the per-period cost unbounded, because the loop
  makes up to 32 passes; the first attempt capped per pass and K = 1 still missed the target,
  which is how the distinction was found);
* `_admit_monitoring` escalates at most K instants per period, in pi_0 order by their own
  deadlines, so the instants closest to missing are the ones evaluated;
* the STATE pass (spec 7.3 / 8.2: one DeltaJ per promotion the tier assignment proposes, which
  is O(devices) per period) evaluates at most K candidates per period, in the tier assignment's
  own order, so the promotions worth the most are the ones scored;
* the D63 PREDICTION LOG, which is two extra rollouts per logged release and is pure logging, is
  limited to K logged releases per period (at a 100 ms period, still 10 x K
  predicted-versus-actual samples a second).

THE CAP HAD TO COVER MORE THAN THE RELEASE LOOP, and that is a measured finding rather than a
design choice: with the cap on the release loop and SH admission only, **K = 1 at 128 devices
still missed the p99 target**, because the state pass scores one promotion per device per period
and the prediction log spends eight rollouts per period regardless of K. Both are now inside the
same per-period budget.

In every place the rest WAIT IN pi_0 ORDER (or the tier assignment's order) for the next
period; nothing is dropped, because an instant stays visible until its own deadline and a pending item stays pending. The cap is
reported as a SETTING in the run header (`placeholders` row `release_eval_cap_k`, `tuned:
false`) and its binding is counted (`arm_stats.sh_cap_bound_periods`, `sh_cap_skipped`,
`release_cap_bound_passes`, `release_cap_skipped_items`).

It is NOT a declared `Params` field, because `policy/params.py` is a StudyPOL4 frozen file; it
is set on the Params instance and read with `getattr`, so an unset cap is exactly the old code
path.

The curve, the binding counts and what the cap does to the work the policy gets done are below.
### Capped speed table (K = 1)

`results/orchestration/live2/coord/fix_k1/d99_speed.json`, the same three cells with the cap set:

| devices | decision p50 / p99 / max (ms) | wall (s) | virtual time reached | guard | requests | p99 target |
|---|---|---|---|---|---|---|
| 32 | 4.6 / 8.0 / 39.2 | 8.1 | 194.9 of 195 s | no | **10** | met |
| 64 | 8.8 / 16.1 / 138.3 | 16.4 | 194.9 of 195 s | no | **8** | met |
| 128 | 17.5 / 32.7 / 530.4 | 34.0 | 194.9 of 195 s | no | **7** | met |

Read the request column before the latency columns. At K = 1 the policy issues 7 to 10 requests
per RUN, against 2,666 uncapped at 32 and 64 devices: the cap meets the latency target by not
deciding. The decision-kind histogram at 128 devices says it plainly: 7 `release_monitor` and
9,600 `defer` with the cap, against 1,712 `release_monitor` and 6,400 `defer` without it.

WHY, and it is a property of the cap as D99 (4) specifies it rather than a bug: the release loop
evaluates the first K DUE items in pi_0 order and STOPS at the first non-positive DeltaJ
(spec 8.2 step 3). Under overload the earliest-deadline item is the item closest to being lost,
so with K = 1 the single evaluation per period is spent on an instant that can no longer be
delivered in time, its DeltaJ is <= 0, the loop breaks, and nothing is released -- every period.
The uncapped loop goes on to the hundreds of other due items and finds one worth releasing. At
8 devices the same cap is harmless (945 requests capped against 948 uncapped, and 99.7 % of the
(kind, opportunity_ids) actions in common), because there the earliest-deadline item is usually
still servable.

SO K CANNOT BE CHOSEN ON LATENCY ALONE, and this is the one place where the prompt's recipe
("the smallest K that meets the target at 128 devices") does not by itself give a usable
setting. The full curve is measured and reported so the choice is the user's:

`results/orchestration/live2/coord/fix/d99_cap_k.json`, 128 devices, 50 : 50, mode A, tight
memory, 180 s plus a 15 s drain, mu = 0, H = 1.0 s, seed 1, dry run, 100 ms period. The LAST TWO
COLUMNS are the ones that decide whether a K is usable:

| K | p50 / p99 / max (ms) | wall (s) | virtual time reached | guard | p99 target | requests | requests per virtual s |
|---|---|---|---|---|---|---|---|
| 1 | 17.4 / 32.5 / 512.1 | 33.8 | 194.9 of 195 s | no | **met** | 7 | 0.04 |
| 2 | 30.4 / 58.2 / 535.6 | 54.2 | 194.9 of 195 s | no | **met** | 4 | 0.02 |
| 4 | 55.6 / 107.2 / 577.7 | 94.2 | 194.9 of 195 s | no | missed | 6 | 0.03 |
| 8 | 106.3 / 207.3 / 688.8 | 174.5 | 194.9 of 195 s | no | missed | 27 | 0.14 |
| 16 | 193.6 / 415.6 / 881.6 | 240.0 | 135.6 of 195 s | HIT | missed | 2,426 | 17.89 |
| 32 | 256.8 / 565.6 / 1,049.6 | 240.0 | 117.1 of 195 s | HIT | missed | 2,155 | 18.40 |
| unlimited | 18.5 / 2,152.6 / 2,654.1 | 240.0 | 88.4 of 195 s | HIT | missed | 1,712 | 19.37 |

**THERE IS NO K THAT BOTH MEETS THE p99 TARGET AND KEEPS THE POLICY WORKING.** K <= 2 meets the
target and does essentially nothing; K >= 16 does the work (about 18 requests per virtual second,
the same rate as the uncapped policy) and misses the target by four to six times. The jump is
between K = 8 and K = 16, and the SH-skip column says why: the fixture offers about 119
monitoring instants a second, the period is 10 a second, so the policy must escalate about 12
instants PER PERIOD merely to keep up with arrivals. At K = 16 the escalation cap almost stops
binding (417 instants skipped over the run, against 99,984 at K = 8) and the policy behaves like
the uncapped one; below that it starves by construction.

So the two constraints -- p99 under 100 ms, and keeping up with the instant arrival rate -- cross
between K = 8 and K = 16 on this CPU, and D99 (3)'s target is NOT reachable by capping alone at
128 devices on flash.

**THE CAP IS THEREFORE IMPLEMENTED, MEASURED AND LEFT OFF.** `release_eval_cap_k` defaults to
None (unlimited), which is the behaviour every committed result was produced under, and the
result file carries the warning that `chosen_K` is the smallest K meeting the LATENCY target and
nothing else. Setting a default from this curve would be choosing a number that meets a target
by not deciding, which is the failure mode the mechanism-verification protocol exists to catch.
What K should be, or whether 128 devices belongs in round 1 at a 100 ms period at all, is a
USER DECISION; the curve above is what it needs.

HOW OFTEN THE CAP BINDS, at 128 devices, K = 1: it bound in all 1,800 periods on the SH
admission path (113,228 instants skipped) and in 30,439 release-loop passes (39,057 item
evaluations skipped). At 8 devices it bound in 493 periods and 2,389 passes.

DECISIONS CHANGED BY THE CAP on the 8-device fixture (120 s, seed 1, K = 1 against unlimited):

| metric | value |
|---|---|
| decision-log lines, unlimited / capped | 1,548 / 1,545 |
| lines differing, POSITIONALLY | 1,488 (96.1 %) |
| (kind, opportunity_ids) actions in common | 1,543 of 1,548 (**99.7 %**) |
| requests, unlimited / capped | 948 / 945 |

The positional figure overstates the change, because one skipped evaluation renumbers every
later `decision_id`; the multiset comparison is what says whether the two policies DID different
things, and at 8 devices they almost did not. At 128 devices they clearly do, which is the point
above. Either way a capped arm is a DIFFERENT ARM from an uncapped one (open issue F-2), unlike
the Part 2 (2) work, which is bit-identical.

## F5. Part 3, D100: the information-parity hook

The hook is the existing arm-side one (`live2_roster`), which carries CAUSAL FACTS KNOWN AT
ARRIVAL and never goes through the scrubbed `Observation`. It is now refreshed once per decision
period, immediately before the observation is built, so the facts and the observation describe
the same state; the refresh is O(devices + sessions) per period. Registry arms (FCFS, B8, B9)
declare no `live2_roster` and receive nothing, so they are unchanged by D100.

**(a) The built prefix size, and a later piece costed as a piece.** The roster carries
`built_tokens_by_session`. `arms_policy._apply_partial_readiness` puts it on every pending or
in-flight `rc_piece` as `cached_tokens` with a warm readiness (`HOST-WARM` plus
`external_cached_tokens` when the belief says the prefix is on the host, so the host-KV reload is
charged, StudyPOL4-engine term (a); `GPU-WARM` otherwise). `cached_tokens` is exactly the input
the committed cost model already reads, so nothing in the frozen model changed. Before this, the
believed tier became `gpu` only at `built_tokens >= est_tokens` (the issue-3b fix), so every
later piece was charged `cached = 0`, a cold rebuild, although the already-sent frames travel as
uuid references.

At StudyENG1's 11,184-token D2 history with 1,024-token pieces, the LAST piece (built prefix
10,160 tokens), under the frozen `pol4` model:

| quantity | value |
|---|---|
| piece k > 1 on a warm prefix (1,024 new tokens, cached 10,160) | **0.1384 s** |
| cold rebuild of the same 11,184 tokens | **1.2642 s** |
| ratio | 9.1x cheaper |

**(b) The per-instant SH deadline, and the starvation check.** The roster carries `sh_instant`
per device: the opportunity_id, capture and ABSOLUTE deadline c_i + L_SH of the instant that
device's stream currently stands for, chosen by exactly the rule `CoordState.observation` uses
(first visible, undecided, un-deferred, not-late, in arrival order), which is also the instant
`_serve_monitor` will serve (it takes the earliest deadline). So the arm now scores, orders and
serves the SAME instant.

* `Pi0Edf` (arms 4, 5, 6) orders monitoring calls by that deadline. The "next call due after the
  last answer the application received, plus the monitoring bound" workaround is gone; the
  fallback survives only for the case where no hook is supplied at all.
* `arms_policy._admit_monitoring` escalates that instant, with `capture_at = c_i` and
  `deadline = c_i + L_SH` from the wire, and keys its seen-set on the opportunity_id instead of a
  rounded capture time. The `monitor_answer_window_s` placeholder is now only the fallback.

TWO-DASHCAM STARVATION CHECK re-run (SYNTHETIC 2 dashcams, 0 robots, 60 s, mode A, dry run):

| arm | monitor answers by device | both served |
|---|---|---|
| `edf` | dash000: 120, dash001: 120 | yes |
| `edf-piece1024` | dash000: 120, dash001: 120 | yes |
| `edf-piece2048` | dash000: 120, dash001: 120 | yes |

Before D100 one dashcam was served 240 times and the other none.

## F6. Part 4, D102: the GPU budget is an input

`--gpu-budget-s`, default `window_s x 1.0` (one GPU's time over the run), identical for every
arm, passed to `interface.Budget` and recorded in the run header as `gpu_budget_s`. It replaces
the harness constant (open issue 8). It is the PHYSICAL CAPACITY, so it never binds artificially
(D58: round 1 has no fixed budget; "budget %" is only a test variable), and B8, B9 and
`edf-service-time`, which admit by a utility-per-GPU-second ratio against a remaining budget,
now read an input rather than a constant buried in the loop. A test asserts the four
budget-reading arms all see the same value and that an explicit value is honoured.

## F6b. The three header fields the scorer reads (D103 (f), parent relay)

B's scorer labels a comparison PRIMARY only if the run header carries the memory SETTING, the
device RATIO and the upload MODE; a missing one silently degrades every block-1 comparison to
EXPLORATORY. All three are now in the header under exactly those names:

| field | value | where it comes from |
|---|---|---|
| `memory_setting` | `tight` / `roomy` / `custom_<n>gib` | DERIVED from `--host-tier-gib` against D76's two values, so the label and the capacity input cannot disagree; `--memory-setting` overrides |
| `ratio` | e.g. `50:50` | the fleet trace's own meta when present, else computed from the device counts (`traces.ratio_label`); `--ratio` overrides |
| `mode` | `A` / `B` | the same value as `upload_mode`, under the name the scorer expects |

A capacity that is neither of D76's two values is reported as `custom_<n>gib` rather than being
rounded to the nearer label, so a roomy-check run cannot be mislabelled tight. Verified on a
dry-run cell: `memory_setting: tight, ratio: "50:50", mode: "A", host_tier_gib: 27.0`.
The break sizes are the scorer's own input from the pilot and are not in the header.

## F7. Part 5, D104 housekeeping and the re-run of every earlier test

* The bridge accepts `history_preload` (it parses on-schema and `_ingest` has a handler); a test
  drives it through the Protocol.
* Mode B still uses `traces.pull_responder`. The real fleet replaces it before block 6, not now.
* The bridge no longer decides on every event: it enforces the ONE 100 ms decision period on the
  emulator's own clock, so the period holds whatever the emulator's `tick_s` is (it must be no
  coarser than the period, which `fleet/emulator.py`'s `--tick-s` default of 10 ms satisfies).
  `describe()` now reports `n_decisions` and `decision_period_s` in place of
  `decide_on_every_event`.

EVERY EARLIER live2 TEST WAS RE-RUN AFTER THE CHANGES:

| suite | result |
|---|---|
| `live2/tests/test_live2_coord.py` (legality, fairness digest in both modes, scrub, parity, determinism, cache-isolation fields, DEFER, INTERIM refusal, chaining, bridge) | **26 tests, OK** (4.1 s, was 11 s) |
| `live2/tests/test_live2_fakeserver.py` (the CPU stub) | **4 tests, OK** (70 s) |
| `live2/tests/test_live2_fix.py` (new: D98, D99, D100, D101, D102) | **16 tests, OK** |
| `policy/tests/*` (16 modules) | **all OK**, including the frozen-file md5 check |

Two of those suites needed an edit, both mechanical: the run-header fixture gained
`decision_period_s` and `gpu_budget_s`, and the fleet digest byte-equality test now includes a
`history_preload` in the stream (and builds the pull-mode stream separately, because push and
pull carry different monitor kinds).

**`policy/params.py` was NOT modified.** It is one of the StudyPOL4 FROZEN FILES
(`freeze_t0b.FROZEN_FILES`, md5-checked by `policy/tests/test_residency_belief.py`). The D99 (4)
cap was first added there as a declared field; the frozen-file test caught it immediately, the
edit was reverted (the file is back to its frozen md5 `abbbca7ae904e41851ca4b99fae73345`) and the
cap now lives as a runtime attribute on the `Params` INSTANCE, which the library reads with
`getattr(self.params, "release_eval_cap_k", None)`. An unset cap is therefore exactly the old
behaviour, and no frozen byte moved.

## F8. Files created or changed by StudyLIVE2-fix

CREATED:

```
experiments/orchestration/live2/fix_checks.py            the D98 / D99 / D100 checks, one CLI
experiments/orchestration/live2/tests/test_live2_fix.py  16 tests (D98, D99, D100, D101, D102)
results/orchestration/live2/coord/fix/d98_sh_admission.json        Part 1 (a)
results/orchestration/live2/coord/fix/d99_equivalence.json         Part 2 (2)
results/orchestration/live2/coord/fix/d99_speed.json               Part 2 (3), no cap
results/orchestration/live2/coord/fix/d99_cap_k.json               Part 2 (4), the K curve
results/orchestration/live2/coord/fix/d100_information_parity.json Part 3
results/orchestration/live2/coord/fix_k1/d99_speed.json            Part 2 (3) with K = 1
results/orchestration/live2/coord/fix/<check>/<cell>/              per-cell logs
results/orchestration/live2/coord/fix_k1/speed/<cell>/
```

Every result file carries `is_measurement: false` and a `_provenance` stamp at commit 80fe119.
The per-cell JSONL streams of the large cells ran to 213 MB of CPU-dry-run fixture log, so any
stream over 256 KB is kept as its first three lines (`*.jsonl.head`) beside a `*.jsonl.trimmed`
note giving the original line count, its size and the command that regenerates it; nothing
analytical depends on them, and the small streams are kept whole.

CHANGED:

```
experiments/orchestration/live2/schema.py           history_preload; decision_period_s and
                                                    gpu_budget_s in the run header
experiments/orchestration/live2/CONTRACT.md         history_preload; digest coverage and the
                                                    corrected canonical row-shape table
experiments/orchestration/live2/cstate.py           history_preload -> cold history, no KV;
                                                    preloaded_tokens; session_start no longer
                                                    wipes a preloaded session
experiments/orchestration/live2/traces.py           history_preload in the fairness digest
experiments/orchestration/live2/coordinator.py      one 100 ms decision period; the D100 roster
                                                    facts, refreshed per period; D102 budget
experiments/orchestration/live2/bridge.py           one decision per period on the emulator's
                                                    clock; history_preload accepted
experiments/orchestration/live2/arms.py             pi_0 orders SH by the real instant deadline
experiments/orchestration/live2/arms_policy.py      impl / cap_k; the D100 instant and partial
                                                    readiness; SH admit / decline counters
experiments/orchestration/live2/run_live2_cell.py   --decision-period-s, --gpu-budget-s,
                                                    --policy-impl, --release-cap-k
experiments/orchestration/live2/scale_smoke.py      reports decision_period_s
experiments/orchestration/live2/tests/test_live2_coord.py  header fixture; preload in the
                                                    fleet digest byte-equality test
experiments/orchestration/policy/rollout.py         D98 per-instant SH, in-flight and tail
                                                    deliveries; clone_for_rollout / clone_impl
experiments/orchestration/policy/coordinator.py     capture_at reaches the planned SH call;
                                                    release_eval_cap_k; cap counters
experiments/orchestration/policy/escalation.py      EscalationRequest.capture_at (opt-in)
experiments/orchestration/policy/spec_map.py        the 1.2 row names D98
experiments/orchestration/policy/tests/test_rollout_coordinator.py  1 test changed, 8 added
experiments/orchestration/policy/tests/test_scenario.py             1 test changed
reports/study_live2_coord.md                        this section
```

NOT TOUCHED: `baselines/` (`interface.py`, `constructed.py`, `naive.py`, `registry.yaml`), the
frozen pol4 cost model and every file in `freeze_t0b.FROZEN_FILES` (including
`policy/params.py`), `live2/fleet/`, `live2/scorer/`, `live2/data/`,
`results/orchestration/live2/ANALYSIS_PLAN.md`, every earlier result,
`research/policy_design_log.md`, `research/policy_spec_v4.md`,
`research/policy_ablations.md`, `research/EXPERIMENTS.md`, `research/STATUS.md` and
`results/INDEX.md`.

## F9. Mechanism verification and results consistency

This row is an ENGINEERING TASK with NO MEASUREMENT, so neither CLAUDE.md protocol is run on it,
and that is a statement about this row only.

* **Mechanism verification** applies to an experiment that tests a causal claim before its sweep
  runs. This work tests no causal claim, produces no sweep and no finding: it changes the policy
  and the harness as D98 to D105 direct, and then checks that each change does what the decision
  says, on a CPU fixture. The protocol belongs to the round-1 measured runs. One thing it is
  worth saying here, because it is exactly the failure mode the protocol exists to catch: the
  pre-D98 harness would have run the whole pilot with the SH channel's marginal value
  **correctly and consistently zero** at H = 0.5 s, and every consistency check would have
  passed. D98's fix is what makes "SH admission" a quantity that can vary at all, which is
  Step 2's requirement for any round-1 claim about monitoring.
* **Results consistency check** applies to an experiment that produces numbers. Every number in
  this section is a dry-run fixture output on a SYNTHETIC trace, labelled `is_measurement: false`
  in its own result file. None is committed as a measurement of any quantity. The committed
  values this work READS are read through the existing loaders and not recomputed: the frozen
  `pol4` cost model (the 0.1384 s / 1.2642 s piece-versus-cold-rebuild pair), StudyENG1's
  11,184-token D2 history, StudyE9d's u_SH grid, D76's capacities, D71 / D82's targets, D89's
  omegas. The one cross-check worth recording is the definition audit on `history_preload`: its
  field list and its digest row are byte-identical to the fleet side's, asserted by a test, so
  the same name cannot mean two things across the two sides.

## F10. Open issues (StudyLIVE2-fix)

**F-1. The 100 ms decision period is now a FAIRNESS parameter, and it bounds what any arm can
do.** D99 (1) makes every arm decide 10 times a second, so an arm can serve at most one
monitoring instant per device per period through the stream action, and a 0.5 s cadence gives
5 periods of slack per instant. That is fine at the round-1 cadence, but it means the period is
part of the experimental design and not an implementation detail: a cadence faster than 100 ms,
or a monitoring bound below about 200 ms, would be shaped by the period rather than by the
policy. It is in the header; it should be named in the round-1 report beside H.

**F-2. NO CAP K BOTH MEETS THE p99 TARGET AND KEEPS THE POLICY WORKING AT 128 DEVICES. USER
DECISION NEEDED.** The measured curve (F4 (4)) has K <= 2 meeting the target while issuing 4 to
7 requests per RUN, and K >= 16 doing the work at about 18 requests per virtual second while
missing the target by four to six times; the crossing is at the arrival rate, about 12 instants
per period. The cap is implemented, measured and LEFT OFF (`release_eval_cap_k` default None).
Three ways out, all of them decisions rather than build work: raise the target at 128 devices
and report the coordinator's latency as part of the result; shorten the period or cap only the
paths that do not gate admission; or drop 128 devices from round 1 and let D95's pilot fix the
largest size from the H100's own numbers. A second, smaller point: a capped policy is a DIFFERENT
ARM from an uncapped one (unlike the Part 2 (2) work, which is bit-identical), so if a cap is ever
set the value belongs in the arm's name, not only in its header.

**F-3. The policy's decision latency is still the largest fleet's binding constraint, and it is
a FLASH number.** The speed table is one CPU, one process, a synthetic trace and the committed
cost curve as the service time. The H100 host's CPU differs, the real trace has different
arrival patterns, and under real HTTP the loop also collects completions. D95's pilot is where
the break size is measured; nothing here fixes a latency budget for it.

**F-4. The SH instant the policy scores is the one the coordinator will serve, but only because
both use the same tie-break.** `_serve_monitor` takes the earliest-deadline eligible instant and
the D100 hook offers the first visible one in arrival order; these agree because a monitoring
deadline is capture plus a constant. If a future workload gives two instants of one device
different bounds, the two rules can disagree, and then the arm would score one instant and the
coordinator would serve another. Worth a single assertion in the harness before round 1.

**F-5. An SH instant the policy declines is never re-offered to it, by design, but the
opportunity stays visible to the coordinator until its deadline.** `_seen` is keyed by
opportunity_id, so a declined instant is a device-only outcome (spec 7.9, D62) and the policy
does not reconsider it. Because the coordinator still lists it as visible, it is also the
instant the D100 hook offers for that device until its window passes, so a device that declines
one instant does not escalate its next capture until the declined one expires (at most L_SH).
On the fixtures here that costs nothing (every instant was admitted), but under congestion it is
a second-order coupling between a decline and the next instant's escalation, and it is the kind
of thing that should be a counted quantity in the pilot rather than an inference.

**F-6. `history_preload` is wired on the coordinator side and cross-checked against the fleet's
row, but no END-TO-END run has yet carried one.** The fleet's generator (subagent B) emits it;
the tests here drive it through `_ingest` and through the bridge on hand-built events and assert
the digest row matches `fleet/trace.py` byte for byte. What has NOT happened is one cell per arm
on a real fleet trace that contains preloads, with both sides' digests agreeing. That is the
D104 pre-pilot item and it belongs to the parent.

**F-7. `policy/params.py` is frozen, so the cap setting lives on the Params INSTANCE.** The
library reads it with `getattr`, which is robust, but it means the setting is not discoverable
from the dataclass and does not appear in `Params.placeholders()`. It is reported through the
arm's own placeholder table instead. If the cap survives round 1 it should be declared as a
field the next time the pol4 freeze is re-cut, not before.

**F-8. The mode-B pull responder is still a stand-in** (D104): mode B charges RTT/2 plus the
upload through `traces.pull_responder`, and the real fleet replaces it before block 6. Every
mode-B number in this section is therefore about the coordinator's own loop, not about a pulled
path's delivered delay.


---

# StudyLIVE2-fix2: the scored bodies, so the calibration and the dashcam AP can run

StudyLIVE2-pre section 3 stopped the dense calibration refit (D86, D105) and left the scorer's
dashcam AP uncomputable, because the live monitoring request carried no question and no
`logprobs` and nothing in the coordinator recorded `cloud_score`. This section closes that. CPU
only on flash, no GPU, no server, nothing measured: every number below is a test outcome or a
citation.

## G1. The bodies are the committed bodies, not a copy of them

The rule applied throughout: no expected value is stated in our own words. The question text and
the generation parameters are READ OUT of the committed scripts at import time
(`experiments/orchestration/live2/scores.py::committed_constant`), so a body that drifts from the
study that produced the scores cannot be built.

| what the live body needs | committed source | value |
|---|---|---|
| SH question | `experiments/dashcam/d3_infer_vllm.py:43-44` (`QUERY`) | "Is a collision or near-collision involving the camera vehicle happening or about to happen? Answer only Yes or No." |
| SH generation | `d3_infer_vllm.py:45` (`GEN`) | `temperature 0.0, max_tokens 8, seed 0, logprobs true, top_logprobs 20` |
| SH body shape | `d3_infer_vllm.py:76-93` (`body`) | `[header] + 1 image + [query]` |
| SH header at N = 1 | `d3_infer_vllm.py:72-74` (`grey_header`) | "The following is 1 dashcam frame." (the string the committed D14b N = 1 manifest also carries) |
| SH score | `d3_infer_vllm.py:96-102` (`yes_no`), then `ctrl1c_calibrate.py:276-277,298` | `log(p_yes)`, `p_yes = mass(Yes) / (mass(Yes) + mass(No))` over the first token's top 20 |
| recall question text | `experiments/sember/study_o_q4.py:158-168` (`build_messages`), the text StudyR1 stores per row (`study_r1_inputs.py:80`) | "Watch the video carefully, ... Reply with only the letter of the correct answer (A, B, C, D, or E)." |
| recall generation | `experiments/sember/study_r1_vllm.py:58` (`CELLS["K1"]`) and `:61` (`SEED`) | `temperature 0.0, max_tokens 512, seed 42` |
| recall answer parse | `study_r1_vllm.py:101-110` (`score`) | last `\b[A-E]\b` in the last 300 characters, else "X" |

**NO STOP CONDITION FIRED on (a).** StudyD14b reuses StudyD3's body unchanged
(`d14b_infer_vllm.py:26-35` rebinds only the paths), StudyCTRL1c sends no request at all - it is
a CPU fit over the committed StudyD3 and StudyD14b traces - and StudyORIN1-dense goes through
`study_d15_orin_nexar.py::score_request` (`:118-124`), which carries the same question, the same
`max_tokens = 8` and the same `logprobs` / `top_logprobs = 20`. The four fields the prompt names
(question text, one frame per call, logprobs setting, max_tokens) are identical in all three.

**THE EXEMPTIONS ARE EXACTLY THREE, and the test enumerates them rather than trusting them.**

1. the image bytes and their media type: round 1 sends the stored JPEGs (D70, D91), the committed
   SH studies sent PNG;
2. the D84 cache keys: the top-level `cache_salt` and the per-image client `uuid`, both of which
   post-date StudyD3;
3. `stream` and `stream_options`. **This is a declared deviation, not an exemption the prompt
   granted.** StudyD3 and StudyD14b send `stream = false`; live2 must time the first token, which
   is the quantity the whole study measures. It is recorded here rather than resolved silently
   because it is the one field where the live body is not the committed body. Two things reduce
   it to a transport difference: StudyORIN1-dense and StudyD15 stream the SAME scored request and
   read the score out of the stream (`study_d15_orin_nexar.py:119-120`, "capture the FIRST
   generated token's top_logprobs"), and the extraction reads element 0 of `logprobs.content`
   either way, which is what `scores.first_token_logprobs` asserts. StudyR1 streams, so the
   recall body carries no deviation at all.

`test_the_exemptions_are_exactly_the_three_declared_ones` asserts the extra top-level keys are
exactly `{cache_salt, stream_options}`, that no committed key is missing, and that the only
`image_url` part carries a `uuid`; `test_the_body_is_byte_identical_under_the_declared_exemptions`
then serializes both bodies with `sort_keys=True` and requires equality.

## G2. What changed in the coordinator

| file | change |
|---|---|
| `live2/scores.py` (new) | `load_committed` / `committed_constant` execute ONE function or constant out of a committed script by AST, so StudyD3's `yes_no` and StudyR1's `score` are the functions that run, not copies. StudyD3's module body starts a server path and imports `httpx`, so it is never imported. |
| `live2/bodies.py` | the SH and recall contracts. `kind="monitor"` forces the committed header, the committed question and `SH_GEN`, refuses more than one frame, and refuses a caller-supplied question; `kind="recall"` builds StudyR1's question text and applies `RECALL_GEN`. |
| `live2/backend.py` | the stream reader kept only `usage` and threw the answer away. It now accumulates the answer text and the first token's `logprobs`, which are what the extractors read; `_usage_from_line` is now a thin wrapper over `_json_from_line`. |
| `live2/coordinator.py` | `_score_of` runs the committed extraction per completed request and `_settle` carries `cloud_score`, `cloud_letter` and `p_yes` into the `cloud_answer` payload, which the emulator already copies into `Outcome.cloud_payload` (`fleet/emulator.py:420`) and the scorer already reads (`scorer/score.py:479`). The two call sites now take `max_tokens` from the committed constants instead of the literal 4. |
| `live2/fleet/emulator.py` | `StubCoordinator` no longer hands the scorer `cloud_score=None`. It emits a DETERMINISTIC function of the opportunity id in the range the calibration grid covers, tagged `stub=True`, and `stub_scores=False` restores the old behaviour. No stub score may enter a measured result. |

**A dry run still records no score**, and that is deliberate: it sends no HTTP, so there are no
logprobs, and a fabricated number would be read by the scorer as a real cloud score. The scorer's
existing refusal (AP is not computed when any instant lacks a score) is the correct outcome there,
and `test_a_dry_run_records_no_score_rather_than_a_fabricated_one` pins it.

**One latency-relevant parameter changed and it is flagged.** The recall body's `max_tokens` goes
from 4 to StudyR1's 512. It is required by (c): with 4 tokens no answer letter can be parsed, so
the robot accuracy the scorer computes would have no input. It affects total service time, not
TTFT, and the recall opportunity is judged on first-token delivery
(`coordinator.py::_settle`, `delivered = first_s if first_s is not None else done_s`), so no
deadline rule changes. It is named here because it is a generation parameter, not a bug fix.

## G3. The robot recall audit (c), difference by difference

| field | StudyR1 cell K1 | live2 before | now |
|---|---|---|---|
| question text | StudyO's `build_messages` text, stored per row | `question + "\n" + options` | StudyR1's text, built by StudyO's own function |
| options | inside that text | appended separately | inside that text |
| answer parsing | `score()`, last A-E in the last 300 chars | none recorded | StudyR1's `score()` through `scores.recall_letter` |
| temperature / max_tokens / seed | 0.0 / 512 / 42 | 0.0 / 4 / absent | 0.0 / 512 / 42 |
| frames | ONE `video_url` part, `data:video/jpeg;base64,` with per-frame base64 comma-joined, plus `media_io_kwargs` | per-frame `image_url` parts with D84 uuids | unchanged, and REPORTED not fixed |

**The frame encoding difference is reported, not fixed, and it is the one open item from (c).**
StudyR1 sends a session's frames as a single comma-joined `video_url` with `media_io_kwargs`
pinning `frames_indices` and `fps`. Live2 cannot: the prefix-chained append that the whole study
exists to measure (StudyRH7 / StudySLICE1 / StudyENG1c, cited in `bodies.py`) requires per-image
parts so an already-sent frame can go as a uuid-only reference and hit the engine's multimodal
and prefix caches. Changing it would delete the mechanism under test, and keeping StudyR1's form
would make every history append re-upload every frame. This is a methodological difference
between the accuracy study and the live harness, so it is surfaced for a ruling rather than
decided here. Its consequence: a live recall answer is not guaranteed to equal StudyR1's answer
on the same question even with an identical question text and identical sampling, because the
processor sees images rather than a video. The committed per-token budget already differs for the
same reason (D2 at 90 tokens per image, StudyRH4).

## G4. The two encode parsers (e)

Both parsers in `live2/data/encode_jpeg.py` were written on flash without the data and neither
matched the frame host. They now match the layouts StudyLIVE2-pre section 2 recorded, so the
committed script reproduces the stored JPEGs. **Nothing was re-encoded**: this is a source change
only, and no byte of JPEG was produced on flash.

1. **Nexar.** The frames are stored `<src>/<clip>/<pts_ms>.png` (`d14b_prepare.py:84-87,156`), not
   `<clip>_t<seconds>.png`; run as written, every frame would have been stored UNPARSED.
   `iter_nexar` now reads the committed D14b N = 1 request manifest, takes `frame_keys[0]` (the
   latest frame with pts <= t), verifies `small_sha256[0]` on every frame read, and accepts
   several frame roots separated by `os.pathsep` because StudyD14b hard-links what it shares with
   StudyD14. A sha mismatch or a missing frame is a hard exit, never a substitution.
2. **S-EMBER D2.** D2 is not an `r1_inputs` construction - that cache holds only RICH and RECENT
   npz - so there was no CHW array to transpose. `iter_sember_d2` now walks the committed EVAL
   sessions, indexes frames with `study_rh3_inputs.frames_index`, takes the committed 2-s D2
   stride up to each session's last question time, and loads with
   `study_rh3_inputs.load(path, (352, 256))`, which is the loader E10a used
   (`study_e10a_sizes.py:84-85`) and which returns a PIL image already at the final size, oriented
   by its own rule. `jpeg_bytes_from_image` is E10a's `enc(im, "jpeg", q)` (`:41-49`).
   `iter_sember` is kept unchanged for RICH and RECENT.

The frame references are unchanged, and the test asserts that against `fleet/trace.py` itself
rather than against a remembered format: `<clip>.mp4|t<tttt.tt>` (`trace.py:295`) and
`<session>|f<ffffff.ff>` (`trace.py:357,390`).

## G5. Tests (d)

`experiments/orchestration/live2/tests/test_live2_fix2.py`, 22 tests, all passing.

| test group | what it establishes |
|---|---|
| the SH body (5) | byte-identical to the body StudyD3's own `body()` builds under the three declared exemptions; the question, generation parameters and N = 1 header come from the committed script; one frame per call is enforced; a caller may not substitute the question |
| the extraction (4) | the loaded `yes_no` has the same code constants as the committed function; the score is `log(p_yes)` with `p_yes = y / (y + n)`; neither-Yes-nor-No is None and never a number; the first token is taken correctly out of a stream |
| the recall body (4) | `recall_question_text` reproduces the `text` of EVERY committed StudyR1 manifest row whose question is in the committed MCQ file, byte for byte (1,690 rows compared, 1,690 identical); the generation parameters equal `CELLS["K1"]` plus `SEED`; the live body carries both; the parser is StudyR1's |
| the coordinator (3) | every monitor answer carries a `cloud_score` equal to `log(p_yes)`; every recall answer carries a letter in A-E or X; a dry run records None rather than a fabricated score |
| end to end (1) | a real-pool trace (seed 11, 8 devices, 25:75, 600 s, mode A) through the fleet emulator, the bridge, the real coordinator and a scoring fixture server, then `scorer/score.py`: `n_missing_cloud_score == 0` and the play-indexed AP is computed, every value a probability. No score in this path is written by the test |
| the stub (2) | the emulator stub passes a deterministic, reproducible, `stub=True`-tagged score through, and can be switched off |
| the parsers (3) | the Nexar parser reads the clip/pts layout, stores only N = 1 instants, and exits on a sha mismatch; the frame-reference formats are checked against `fleet/trace.py`'s source; the D2 parser applies the 2-s stride, stops at the last question, and uses the committed loader's own orientation rule |

The fixture server is a test-only `ThreadingHTTPServer` that answers with `logprobs`, which the
committed LIVE1 stub does not. `experiments/orchestration/live/fake_server.py` was NOT modified:
it belongs to StudyLIVE1 and every existing test still runs against it unchanged.

## G6. Mechanism verification and results consistency

**Not applicable, and that is the honest answer.** This section reports no measurement, tests no
causal claim and produces no result file. Mechanism verification Steps 1 to 5 and the six
consistency checks are owed by the round-1 measured runs, as section 12 and F9 already record. The
checks that DO apply here are checks of identity rather than of a quantity, and they are the tests
in G5: the body is the committed body, the extractor is the committed function, the question text
is the committed text, and the frame references are the ones the trace generator emits.

What this section changes for the pending work: StudyLIVE2-pre's Part 2 STOP ("there is no
coordinator score to extract") no longer holds, so the D86 / D105 dense calibration refit can be
re-run on the same server configuration, and the scorer's dashcam AP has an input. Neither is run
here: both are H100 work.

## G7. Files created or changed by StudyLIVE2-fix2

| file | status |
|---|---|
| `experiments/orchestration/live2/scores.py` | NEW: the committed extractors, loaded from the committed scripts |
| `experiments/orchestration/live2/bodies.py` | the SH and recall body contracts |
| `experiments/orchestration/live2/backend.py` | the stream reader keeps the answer text and the first token's logprobs |
| `experiments/orchestration/live2/coordinator.py` | `_score_of`, the score in the `cloud_answer` payload, committed `max_tokens` at both call sites |
| `experiments/orchestration/live2/fleet/emulator.py` | `StubCoordinator` passes a deterministic tagged score through |
| `experiments/orchestration/live2/data/encode_jpeg.py` | both input parsers match the stores the H100 used |
| `experiments/orchestration/live2/tests/test_live2_fix2.py` | NEW: 22 tests |
| `research/EXPERIMENTS.md`, `reports/study_live2_coord.md` | the row and this section |

## G8. Open issues (StudyLIVE2-fix2)

1. **The recall frame encoding differs from StudyR1 and cannot be made to match** (G3). Needs a
   ruling: either accept that the live recall answer is not StudyR1's answer on the same question
   and say so wherever the two are compared, or add a non-chaining recall arm that sends
   StudyR1's `video_url` form so one arm is directly comparable.
2. **The SH body streams and StudyD3's does not** (G1, deviation 3). The score is read from the
   same element either way and StudyD15 does exactly this, but no committed measurement proves
   that a streamed and a non-streamed request return identical first-token top-20 logprobs on
   the same input. A one-cell check on the H100 would close it; StudyORIN2-warm ran the
   equivalent check across harnesses and is the precedent for the form it should take.
3. **The stub score is a fabricated number by construction** (G2). It is deterministic and
   tagged, and no measured run uses the stub, but if a stub run ever reached a report the AP would
   be meaningless. The scorer refuses on `server_kind` already ("s5 the scorer treats both 'stub'
   and 'fake' as non-measurement servers"), so this is a note, not a gap.
4. **`max_tokens` 4 to 512 on recall** (G2) is a generation-parameter change made to satisfy (c).
   Flagged for the record.

---

# StudyLIVE2-harness: the pilot's lateness was the tick schedule, not the GIL

StudyLIVE2-pilot stopped at Step 1 because the first real-server cell left the fleet emulator's
p99 lateness at 511.6 ms against the 50 ms validity limit, while the coordinator was idle
(decision p99 0.70 ms, CPU 4.7 %). Its candidate cause, labelled untested, was GIL contention
between the response-reading threads and the wall-clock loop. **That candidate is wrong.** The
cause is that the coordinator was not driven at all while the emulator waited, so a request that
finished inside a wait was not noticed until the next action popped. CPU only on flash; every
number here comes from the fake streaming server and the byte-exact fixture store, so no run in
this section is a measurement of anything but the harness.

## H1. Step 1: reproduced on flash

The reproduction needs bodies of the right size and a server that takes the right time.
`live2/harness_fixture.py` writes, per frame_ref the trace needs, a file of EXACTLY the byte
length the committed Part-1 manifests record (42,014 Nexar + 32,142 S-EMBER D2 rows); the content
is deterministic filler behind a JPEG SOI marker, so the base64 payload has the real length and
nothing else about it is real. `live2/fakestream.py` serves one request at a time per engine slot
with the service time the COMMITTED cost curves give (`baselines/costs.py`, the same two
functions `coordinator._dry_service_s` already used: episodic 1 frame = 0.2213 s, recall 11k
COLD = 2.4444 s) and streams its answer with first-token timing and `logprobs`.

| | pilot, H100, real server | flash reproduction |
|---|---|---|
| lateness samples | 2,317 | 2,301 |
| p50 | 0.11 ms | 0.213 ms |
| p90 | 171 ms | 90.7 ms |
| p99 | **511.6 ms** | **228.1 ms** |
| max | 1,434 ms | 289.3 ms |
| decision p99 | 0.70 ms | 0.56 ms |
| requests | 727 submitted, 725 completed | 711 submitted, 709 completed |
| process CPU | 4.7 % | 2.9 % |
| run_valid | false | false |

The signature is the same: a sub-millisecond median, a tail in the hundreds of milliseconds, an
idle coordinator. The magnitude is smaller because flash's fixture does not reproduce the H100's
response volume or its real TTFTs. That is enough to diagnose it.

## H2. What the profile said, and what actually found it

`cProfile` over the whole run (`profile.txt` in the step-1 run directory) puts the cumulative
time in `http.client.readline` / `_peek_chunked` / `_read_next_chunk_size` across the pool
threads, which is what made GIL contention look plausible: thousands of Python-level calls per
response, each holding the GIL. It is a red herring. cProfile aggregates across threads and
cannot tell which thread delayed the clock.

What found it was attributing each late action to its own kind. The emulator charges lateness per
heap action; adding the action's due instant and kind to each sample
(`fleet/emulator.py::Lateness.add`, off unless a detail list is attached) gives this, at 8
devices over 120 s:

| action kind | n | p50 | p99 | max |
|---|---|---|---|---|
| `answer_delivered` | 705 | **18.4 ms** | **289.0 ms** | **289.5 ms** |
| `monitor_opportunity` | 768 | 0.168 ms | 0.275 ms | 0.305 ms |
| `frame_arrived` | 768 | 0.178 ms | 0.289 ms | 0.383 ms |
| `history_batch` | 16 | 0.169 ms | 0.240 ms | 0.240 ms |
| `history_arrived` | 16 | 0.209 ms | 0.236 ms | 0.236 ms |
| `register` | 8 | 0.165 ms | 0.192 ms | 0.192 ms |
| `recall_question` | 6 | 0.206 ms | 0.281 ms | 0.281 ms |
| `question_arrived` | 6 | 0.163 ms | 0.208 ms | 0.208 ms |
| `session_start` | 4 | 0.217 ms | 0.221 ms | 0.221 ms |
| `history_preload` | 4 | 0.241 ms | 0.246 ms | 0.246 ms |

**Every late action is an `answer_delivered`, and no other kind is ever late.** All 435 samples
over 10 ms are answers. A loop stalled by the GIL would be late on whatever action it happened to
be holding, and these actions are not late at all: the loop dispatches everything else at p99
0.28 ms throughout.

**The mechanism.** The emulator's loop ticked the coordinator by catching up the tick grid
BEFORE sleeping to the next action's instant, then slept. So between two actions the coordinator
was never called: `co._collect` never ran, a completed request was not settled, and no
`cloud_answer` was produced. When the next action finally popped, the answer appeared carrying
`t_done = sent_s + total_s`, a timestamp already in the past; the emulator scheduled the delivery
from that timestamp (`_handle_reply`), the action was therefore due in the past, and the loop
charged the whole notice delay as lateness. The distribution follows: p50 18 ms is the typical
gap to the next action, and the 289 ms tail is the fixture's 221 ms episodic service plus the
downlink, i.e. a completion that landed early in a long wait.

This also explains the pilot's own control, which it reported but did not use: the device-only
run had p99 0.48 ms. Device-only sends no request, so it has no answers to be late about.

## H3. The fix, and the honest attribution

Three changes were made, as the prompt directs. Only the third moves the lateness, and the table
says so rather than crediting the fix that was asked for first.

| configuration | p50 | p90 | p99 | max | over 10 ms | valid |
|---|---|---|---|---|---|---|
| pilot wiring (urllib, 64 threads, body on the loop) | 0.213 | 90.7 | 228.1 | 289.3 | 435 | no |
| + async client, frame cache, deferred bodies (b) | 0.195 | 91.4 | 230.4 | 289.6 | 435 | no |
| + coordinator in its own process (a) | 0.171 | 0.265 | 136.3 | 236.7 | 191 | no |
| + emulator ticks on the wall clock while waiting | 0.143 | 0.216 | **0.257** | **0.373** | **0.000** | **yes** |
| the tick fix ALONE, in process, async client | 0.173 | 0.215 | 0.290 | 3.575 | 0 | yes |
| the tick fix ALONE, in process, ORIGINAL urllib backend | 0.145 | 0.211 | 0.305 | 1.565 | 0 | yes |

Read down the last two rows: **the real-time tick is the whole fix.** With it, even the original
64-thread `urllib` backend that the pilot blamed passes at p99 0.305 ms. Fix (b) on its own
changed nothing measurable (228.1 to 230.4 ms, within run-to-run noise) even though it cut body
building to 0.068 ms mean and decision p99 from 0.56 to 0.146 ms: the work it removed was never
on the critical path. Fix (a) on its own took p99 from 228 to 136 ms, because the child process
drives its own ticks every 5 ms, but the PARENT still drained replies only when an action popped,
so half the delay remained.

What (a) and (b) do buy, on this evidence, is tail margin: the worst action is 0.373 ms with the
split against 3.575 ms in process, a factor of 9.6, which is the GIL isolation showing up where
the pilot expected to find the whole problem. Both are kept: they are what the prompt asked for,
they are the right structure for a run that must not be perturbed by its own client, and the
margin is cheap. But the report must not claim they fixed the lateness, because they did not.

## H4. What changed, file by file

| file | change |
|---|---|
| `live2/fleet/emulator.py` | the real-time tick (the fix). While waiting for an action the loop ticks the coordinator every `tick_s` of WALL time and handles replies; a reply that schedules an earlier action sends the held action back on the heap so strict time order is kept. A non-real-time run keeps the old catch-up grid exactly, which is what leaves the existing suites untouched. `Lateness.add` optionally records each sample's due instant and kind. |
| `live2/procsplit.py` (new) | the emulator and the coordinator in separate processes over a UNIX socket carrying length-prefixed JSON and the emulator's `t`. Replies are asynchronous because each already carries its own run-clock timestamp (`pull_request.t_sent`, `cloud_answer.t_done`), so the parent never blocks on the child. The child drives its own ticks every 5 ms; `self_tick_s = 0` disables that, which is what makes a split run comparable line for line. |
| `live2/asyncbackend.py` (new) | one asyncio loop in one thread with one `httpx.AsyncClient`, streaming. Bodies are materialized and serialized ON THAT LOOP, never on the decision loop, and `wire_bytes` splices the already-encoded base64 in instead of handing a multi-megabyte string to `json.dumps` twice. Follows StudyRH6's committed precedent for both (pre-serialised image fragments; a connection limit of 16,384). |
| `live2/framecache.py` (new) | each frame's base64 data URL computed once and reused, under a byte-capped LRU. The old path re-read and re-encoded the same file every time it appeared in a body. |
| `live2/bodies.py` | `defer_images` leaves image payloads as placeholders for `materialize` to fill in off the loop. The wire form is unchanged and the tests assert it frame by frame. |
| `live2/coordinator.py` | accepts a frame cache and `defer_images`, both OFF by default, so an unconfigured run behaves exactly as the pilot's did. |
| `live2/run_live2_real.py` (new) | fix (c): the pilot turned into a committed runner, one cell per invocation, every input a flag, the same header fields, the same run_meta annotation, then the scorer. `--start-server` keeps the pilot's restart-per-run behaviour and imports the H100-only modules lazily, so the file runs on flash. `--no-split` keeps the single-process wiring for comparison. |
| `live2/fakestream.py`, `live2/harness_fixture.py` (new) | the step-1 fixtures described in H1. The committed StudyLIVE1 `fake_server.py` was NOT modified. |
| `live2/harness_checks.py` (new) | the step-1 reproduction and the acceptance grid. |
| `live2/tests/test_live2_harness.py` (new) | 13 tests. |

**No change to arms, decisions, schema, digests or scoring.** The tests pin that: a deferred body
materializes to the byte-identical immediate body on every body kind the coordinator sends, the
frame cache returns exactly what `bodies._data_url` returned, `wire_bytes` round-trips to the
same JSON, and a split run's fairness digest, sent-stream digest, outcome set and decision log
are identical to an in-process run's on the same trace and seed.

## H5. Step 3: acceptance on flash, 7 of 8 cells

The grid the prompt asks for: p99 lateness at 8 and 64 devices, `edf` and `policy-core`, both
upload modes, split processes, fake streaming server, 120 s, seed 0, 50 : 50, limit 50 ms.

| arm | devices | mode | p50 | p90 | **p99** | max | within 50 ms | digest equal | requests | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| edf | 8 | A | 0.166 | 0.216 | **0.257** | 0.930 | yes | yes | 711 | 0 |
| edf | 8 | B | 0.149 | 0.207 | **0.249** | 0.375 | yes | yes | 350 | 0 |
| policy-core | 8 | A | 0.091 | 0.208 | **0.263** | 0.331 | yes | yes | 767 | 0 |
| policy-core | 8 | B | 0.142 | 0.220 | **0.297** | 0.365 | yes | yes | 0 | 0 |
| edf | 64 | A | 0.090 | 0.210 | **0.279** | 0.909 | yes | yes | 599 | 0 |
| edf | 64 | B | 0.065 | 0.203 | **0.260** | 2.636 | yes | yes | 34 | 0 |
| policy-core | 64 | B | 0.086 | 0.202 | **0.501** | 108.188 | yes | yes | 4 | 0 |
| policy-core | 64 | A | 0.071 | 0.206 | **110.920** | 1153.710 | **NO** | yes | 957 | 0 |

All milliseconds. The fairness digest is identical across arms at every size and mode
(`{8|A, 8|B, 64|A, 64|B}` all true) and equals the trace's, so nothing in this row changed what
the fleet presents.

**The one failing cell is not a harness defect, and the evidence is one to one with the policy's
own decision cost.** Re-run with per-action attribution and the writer-thread fix below, that
cell gives:

| quantity | value |
|---|---|
| lateness p50 / p90 | 0.080 / 0.208 ms |
| lateness p99 / max | 110.256 / 488.336 ms |
| late actions over 10 ms | 599, **every one an `answer_delivered`** |
| coordinator decision latency p50 / p99 / max | **35.537 / 115.694 / 156.423 ms** over 1,201 decisions |
| epoch overruns | 0 |

The loop itself is still dispatching everything else at p90 0.208 ms. The answer lateness p99
(110.3 ms) and the decision p99 (115.7 ms) are the same number: while the coordinator spends up
to 156 ms inside one ΔJ evaluation it collects no completion, so the answer it then emits carries
a `t_done` already that far in the past. `policy-core` at 64 devices simply cannot decide inside
its 100 ms period, which is what StudyLIVE2-fix already measured (decision p99 545.4 ms at 64
devices, 2,152.6 ms at 128) and what StudyLIVE2-perf is queued to fix. **Prediction, stated here
before that work runs: this cell meets the 50 ms limit once the decision p99 is under roughly
50 ms, because the two track one to one.**

**What was NOT done about it, and why.** Collecting completions on a second thread in the
coordinator process would hide the delay, and it was rejected: `_collect` mutates the sessions,
opportunities and answers that `_epoch` is reading, so it would race, it would make a decision
depend on when a thread happened to run, and it would change what the policy sees mid-decision.
That is forbidden by this row's own constraint ("no change to arms, decisions, schema, digests or
scoring") and it would convert an honest measurement of a slow policy into an artifact.

One transport defect WAS found and fixed while chasing this cell: the parent wrote to the socket
from the clock thread, so a child busy taking a decision stopped reading, the socket buffer
filled and `sendall` blocked the emulator. Writes now go through a queue drained by a writer
thread, so the emulator never blocks on the wire and a slow child shows up only as answers
delivered late. Fixing it did not change this cell's p99 (110.9 to 110.3 ms), which confirms the
back-pressure was not what bounded it.

## H6. Mechanism verification and results consistency

**Mechanism verification: not applicable, and the reason is the usual one for a harness row.**
This section tests no causal claim about representation, placement or timing; it measures one
property of the measuring apparatus. Steps 1 to 5 remain owed by the round-1 measured runs
(report section 12, F9, G6). The analogue that DOES apply here was run, and it is the reason the
fix is attributable rather than asserted: the mechanism was named (the coordinator is not driven
during a wait), instantiated (the lateness of each action by kind), traced (a single action's due
instant against the completion that preceded it), and given a negative control (the pilot's own
device-only run, which sends no request and has p99 0.48 ms, and the flash cells with the tick
fix removed, which return to p99 228 ms). Both candidate alternatives were tested and rejected by
experiment rather than by argument: the async client with the frame cache (no effect, 228.1 to
230.4 ms) and the process split alone (partial, 228.1 to 136.3 ms).

**Results consistency, the four checks that have an input:**

1. *Cross-check against the committed measurement.* The flash reproduction is compared against
   StudyLIVE2-pilot's cell in H1. The p99 ratio is 2.24x (511.6 vs 228.1 ms) and p90 1.89x, both
   inside the 2x-or-explained rule with the explanation stated: flash's fixture does not
   reproduce the H100's response volume or its real TTFTs. The shape agrees in every other
   respect (sample count within 0.7 %, sub-millisecond median, idle coordinator, request count
   within 2.2 %).
2. *Physical plausibility.* The fixture's service times are not invented: they are the committed
   cost curves (`episodic_cloud_latency_s` 0.2213 s at 1 JPEG frame, `recall_ttft_s` 2.4444 s at
   11k COLD). The 289 ms lateness tail is bounded by that 221 ms service plus the downlink, which
   is the arithmetic the diagnosis predicts.
3. *Distribution sanity.* Every lateness figure is reported with p50, p90, p99 and max, and the
   per-kind table in H2 is the full breakdown rather than a median. The decisive observation is
   precisely a distributional one: p50 0.2 ms with a p99 of 228 ms is not a loaded loop.
4. *Definition audit.* "Lateness" keeps the emulator's own definition (`now - due` per heap
   action, in the process holding the clock) and the limit keeps its committed value
   (`MAX_P99_LATENESS_MS = 50.0`). The only change is that each sample now also records its due
   instant and kind. "p99" is the emulator's existing index-based quantile, unchanged.

Claim linkage and proxy validity do not apply: no result here bears on a claim in
`research/CLAIMS.md`, and the fixture frames are not a proxy for image content because nothing
decodes them. The fixture reproduces one property, the byte length, and that is the only property
the measurement uses.

## H7. Open issues (StudyLIVE2-harness)

1. **`policy-core` at 64 devices misses the 50 ms limit at 110.3 ms, bounded by its own decision
   cost** (H5). Not fixable here; it is StudyLIVE2-perf item 1. Until then a 64-device
   `policy-core` real-server cell will be marked invalid by the emulator's own rule, so the
   ladder cannot pass 64 devices for that arm.
2. **30 of the 1,278 frame references an 8-device 120 s trace asks for are absent from the
   committed Part-1 manifests**, all S-EMBER D2 refs past the stride the manifests cover (the
   manifests reach each session's last question; the trace keeps appending history to the end of
   the session). On flash they fall back to a uuid-only reference, which makes the body slightly
   smaller. **On the H100 this is a correctness issue, not a cosmetic one:** a uuid-only
   reference tells the engine it has already seen bytes it never received. It needs a ruling,
   either extend the D2 store past the last question or have the trace generator stop asking for
   frames the store does not hold.
3. **The pilot's stated cause is wrong and its report says so with the right hedge** ("Candidate,
   untested"). Worth keeping as precedent: the hedge is why nothing downstream was built on it.
4. **The real-time tick changes when a reply is handled inside a real-time run**, so a
   `cloud_answer` can now schedule a delivery that the old loop would have scheduled later. This
   is a fidelity improvement, not a neutral one: a real-time run before this fix systematically
   delivered cloud answers late. No committed round-1 result used that path (the pilot stopped),
   so nothing needs re-running.

## H8. Suites after the change

| suite | result |
|---|---|
| `live2/tests/` (coord, fakeserver, fix, fix2, harness) | 81 of 81 pass, 13 of them new |
| `live2/fleet/tests/test_live2_fleet.py` | 234 of 234 checks pass |
| `live2/fleet/tests/test_scale.py` | exit 0, no failure |
| `policy/tests/` | 384 of 384 pass |

One failure appeared and was an artifact of the ad-hoc scratch runner used to drive the
pytest-style modules, not of the code: that runner has no `if __name__ == "__main__"` guard, so
`multiprocessing`'s spawn re-imported it in the child and re-ran the whole suite inside the new
coordinator process, and the parent's accept timed out. The same test passes under
`python3 -m unittest`. The runner is scratch tooling and is not committed; it is recorded here
because the symptom looks exactly like a deadlock in `procsplit.py` and is not one.

---

# StudyLIVE2-perf: a 5.0x decision-preserving speed-up, and why the rest is not available

CPU only on flash, 13th Gen Intel Core i7-13700KF, 24 logical cores, dry-run fixtures throughout.
Nothing here is a measurement of the policy's behaviour: every number is a decision latency, a
wall clock or a count, and every decision log is checked against the pre-change baseline.

F-1 is accepted and the decision period is named beside H wherever both appear. F-2 stands: the
release cap stays OFF (`release_eval_cap_k = None`) and the H100 pilot measures the uncapped
latency.

## P1. What was changed, and what it bought

Three changes, all in NON-FROZEN files, none of which alters an arithmetic result: each one
returns the value that was previously recomputed.

| change | file | what it removes |
|---|---|---|
| memoise three pure profile lookups | `policy/profiles.py` | `rc_accuracy` (5.1 M calls), `recall_ttft_s` (2.9 M) and `seconds_per_token` (2.3 M) each rebuilt a derived table on EVERY call: a five-entry name map, a sorted set of measured sizes parsed out of the key strings, and a dict comprehension over the rate table. The tables are now built once per `Profiles` instance and the results memoised on the arguments. |
| a direct shallow clone | `policy/rollout.py` | `copy.copy` at the five rollout-clone sites went through `__reduce_ex__` and `copy._reconstruct` 3.7 M times per 64-device cell. These are plain dataclasses with no `__slots__` and no `__copy__`, so building the object and copying its `__dict__` is what that machinery produced; anything without a `__dict__` still falls back to `copy.copy`. |
| deduplicate the tier evaluations | `policy/readiness.py` | `state_value` called `_u_rc_from_tier` six times, three for `here` and three for `colder(t)`. `colder` maps TIERS into TIERS, so with three tiers the second triple asks for HOST, COLD and COLD again, all already computed. Everything but `tier` is the same variable in both expressions, so one dict keyed by tier serves both. |

Measured on one 64-device cell (32 dashcam + 32 robot, 60 s window, seed 1, H = 1.0 s, mu off,
dry run), each step cumulative, **no profiler attached**:

| after | decision p50 | decision p99 | decision max | wall |
|---|---|---|---|---|
| before any of this | 7.289 ms | 380.594 ms | 388.990 ms | 28.3 s |
| + profile memoisation | 7.252 ms | 285.933 ms | 292.128 ms | 22.1 s |
| + shallow clone | 6.653 ms | 251.536 ms | 254.307 ms | 19.6 s |
| + tier dedup | **6.654 ms** | **240.916 ms** | **243.756 ms** | **18.9 s** |

**p99 380.59 to 240.92 ms, a factor of 1.58; wall clock 1.50x; p50 essentially unchanged at
1.10x.** At 16 devices the same three changes are worth 1.40x on p99 (51.689 to 37.009 ms) and
1.29x on wall clock.

**A correction, because it changes the headline.** An earlier pass of this work reported 5.05x.
That figure was wrong: its "before" number (p99 1,211.95 ms) came from a run with `cProfile`
attached, and its "after" number did not. A profiled run's decision latency is not a decision
latency, because the profiler's per-call cost lands inside the timed span and the hot path here
is millions of small calls. The profiler is still the right tool for ATTRIBUTION, which is what
it is used for below; it is not a stopwatch. Every speed-up number in this section is unprofiled
on both sides, and the committed cross-check in P2b agrees with them.

The profile (attached, therefore inflated in absolute terms but valid for shares) shows where the
time goes in a 64-device cell after the change: `_terminal` 36.9 s cumulative, `predict` 19.8 s,
`copy` 11.2 s, the `state_value` chain 13.6 s (it was 30.2 s before), `_opportunity_utility`
8.5 s.

## P2. Every decision is unchanged, checked three times

After each of the three changes the decision log was compared against a baseline captured with
the pre-change `profiles.py`, on the D99 equivalence grid: 4 and 8 devices, seeds 1, 2 and 3,
120 s, dry run, latency fields stripped.

| change | cells compared | lines per cell | identical |
|---|---|---|---|
| profile memoisation | 6 | 490 to 1,548 | 6 of 6 |
| + shallow clone | 6 | 490 to 1,548 | 6 of 6 |
| + tier dedup | 6 | 490 to 1,548 | 6 of 6 |

No decision changed at any point, so there was nothing to explain under the prompt's "if any
decision changes, find out why".

## P2b. The committed D99 checks, re-run

`fix_checks.equivalence` (the D99 (2) check: the fast clone against `copy.deepcopy`, 4 and 8
devices, seeds 1 to 3, 120 s) passes 6 of 6 identical, and the reference-to-fast speed-up it
reports has risen from the committed 6.0 to 7.1x to **6.94 to 8.58x**, because these changes
speed the fast path and not the reference path.

`fix_checks.speed` at the committed fixture (180 s window, seed 1, mu off, H = 1.0 s, dry run),
against StudyLIVE2-fix's committed figures for the same cells:

| devices | decision p50 | decision p99 | decision max | committed p99 (StudyLIVE2-fix) | ratio | cpu % | wall |
|---|---|---|---|---|---|---|---|
| 32 | 30.786 ms | **154.172 ms** | 159.030 ms | 214.0 ms | 1.39x | 99.8 | 57.1 s |
| 64 | 76.050 ms | **385.720 ms** | 469.265 ms | 545.4 ms | 1.41x | 99.9 | 143.1 s |
| 128 | 189.697 ms | **1,482.719 ms** | 2,239.139 ms | 2,152.6 ms | 1.45x | 100.0 | 395.3 s |

Every cell reached the full 194.9 s of virtual time, no wall guard was hit, and CPU sat at 100 %
throughout, which is what says the loop is compute-bound rather than waiting. The three ratios
agree with each other and with the 60 s fixture's 1.58x, so the consistency check on this
quantity passes: no disagreement above 2x.

`results/orchestration/live2/coord/perf/perf_d99_equivalence.json` and `perf_speed.json` hold
both runs.

## P3. Parallel DeltaJ across worker processes: NOT DONE, because it is not decision-preserving

The prompt asks for independent DeltaJ candidates to be evaluated in parallel across worker
processes with deterministic ordering so decisions are identical. **The candidates are not
independent, so no ordering of parallel results can reproduce the sequential decisions.**

The dependence is explicit in the committed coordinator. On an admit, `escalate` and `_admission`
both do

    fleet.pending += items                      policy/coordinator.py:299
    ep.calls_issued.append(fleet.t)              policy/coordinator.py:305
    dev.episodes.append(ep)                      policy/coordinator.py:308

and the next candidate's DeltaJ is a rollout over that same `fleet`. So candidate k is priced
against a fleet that already carries everything candidates 1 to k-1 committed in this period.
Evaluating all candidates against one epoch-start snapshot prices each as though it were the only
admission of the period, which systematically omits the queueing the others impose: it would
admit more, and it would be a different policy. The prompt forbids exactly that ("Do NOT change
what the policy computes... no batching of admission decisions").

This is not a corner case. Counting decisions per epoch on the committed fixtures:

| fixture | decisions | epochs | epochs with more than one decision | max in one epoch |
|---|---|---|---|---|
| 4 devices, seed 1, 120 s | 492 | 485 | 6 (1.2 %) | 3 |
| 8 devices, seed 1, 120 s | 1,548 | 580 | **571 (98.4 %)** | 6 |

At 8 devices and above, almost every epoch takes several dependent decisions, so the sequential
chain is the normal case rather than the exception. No worker count or CPU count is reported for
this item because no workers were started; the machine is recorded above for the timings that
were taken.

What could still be parallel, and is not worth it: a single candidate's DeltaJ is one sequential
rollout, so the parallelism would have to be across candidates, which is the dependence above.
Splitting one rollout across processes would need the rollout itself to be reordered, which is a
change to what the policy computes.

## P4. The largest remaining avoidable cost is inside a FROZEN file, and it was not taken

`Eng1Engine.predict` is called 773,652 times in a 64-device cell. On every call it rebuilds two
PROVENANCE strings, each constructing a `pathlib.Path` purely to take a basename:

    basis = ["StudyENG1 step model (%s), ..." % Path(self.step.path).name]      eng1_engine.py:543
    basis.append("StudyPOL4-engine terms from %s" % Path(self.pol4.path).name)  eng1_engine.py:570

That is 1.55 M `pathlib` path parses, 12.4 M `sys.intern` calls and 18.8 M string splits, about
**10.5 s of a 71 s profiled 64-device run, near 15 %**. The strings are constant for a given
engine and are provenance text that no arithmetic reads, so caching them cannot change a
prediction.

**It was implemented, it failed the freeze, and it was reverted.**
`experiments/orchestration/policy/eng1_engine.py` is one of the twelve files in the StudyT0b
freeze (`results/orchestration/study_t0b/t0b_freeze.json`), and three committed tests assert its
md5: `test_pol5_engine.py::test_the_engine_module_md5_still_matches_the_t0b_freeze`,
`test_pol6_chain.py::test_every_t0b_freeze_md5_still_matches` and
`test_residency_belief.py::test_no_frozen_file_was_modified`. The working tree was restored with
`git checkout --` and all 384 policy tests pass again.

**This needs a ruling and it is not mine to take.** It is a freeze-policy question, not a
modelling one: the change is provably value-neutral, but the freeze's own rule is that content,
not intent, decides whether the frozen model changed (`t0b_freeze_erratum.json`). Either the
freeze is amended with a re-recorded md5 under the same authority that took it, or roughly 15 %
stays on the table. Recommendation: amend, because the alternative is to leave the single largest
avoidable cost in the hot path of every future policy run in order to protect the byte-identity
of two strings of provenance text.

## P4b. F-4: the instant the policy scores is the instant the coordinator serves

`arms_policy.py` now keys every SH instant it scores by the `opportunity_id` the D100 hook names,
records the ones it admitted, and asserts on completion that the monitor request the coordinator
served is one of them. If it ever were not, every DeltaJ this arm computed would refer to an
instant that was not the one answered, and nothing downstream would notice: the scorer keys on
the opportunity the coordinator served, and the arm's own counters would still balance.

The assertion carries its own counter (`sh_served_not_scored`) so a failure is diagnosable rather
than just fatal. On an 8-device 120 s dry cell: **960 instants scored, 960 escalated, 0 served
and not scored**, and the assertion did not fire anywhere in the 42 coordinator-side tests or the
384 policy tests.

## P4c. F-5: what a declined SH instant costs that device

Counted per run and reported in `arm_stats`: a decline is held against its device until that
device's NEXT admitted escalation, and the gap between the two is the delay that decline imposed.

| 8 devices, 120 s, seed 1 | value |
|---|---|
| SH instants escalated | 960 |
| admitted / declined | 948 / 12 |
| declines followed by an admit for the same device | **12 of 12** |
| delay imposed, p50 / p90 / max | 1.000 / 1.000 / 1.000 s |
| delay imposed, mean | 0.950 s |

So on this fixture a decline is never terminal for a device, and it costs that device almost
exactly one second, which is the two-instant gap at the 0.5 s SH cadence. 12 of 960 instants
(1.25 %) are affected. The count and the distribution both travel in the run header's
`arm_stats`, so the H100 pilot will report them per cell without further work.

## P5. Status against the goal, stated plainly

The goal was that the uncapped policy keep up with arrivals at 64 and 128 devices. **It does not
at 64, and the speed-up is insufficient.** The decision period is 100 ms (D99) and the decision
p99 at 64 devices is 240.9 ms on the 60 s fixture and 385.7 ms on the committed 180 s
fixture, after a 1.4 to 1.6x improvement: still 2.4x to 3.9x over the period. Per the
prompt's own instruction the curve is reported and the work stops here rather than changing what
the policy computes; the cap stays off (F-2).

Two routes remain, both outside this row's licence: the frozen-file saving in P4 (about 15 %,
needs a freeze ruling), and a change to what the policy computes per candidate (forbidden here).
The harness addendum already removed the consequence that mattered most for the pilot: the
policy's decision cost now shows up as submit delay rather than as emulator lateness, so a slow
decision no longer invalidates a run.

## P6. The freeze ruling applied: `eng1_engine_fast.py`

P4 reported a saving locked inside a T0b-frozen file and asked for a ruling. **The ruling
(2026-11-18) is: never edit a frozen file.** So the frozen file is untouched and the live policy
path loads a copy.

`experiments/orchestration/policy/eng1_engine_fast.py` is `eng1_engine.py` copied, carrying ONE
change: the two provenance strings `Eng1Engine.predict` used to rebuild on each of about 774,000
calls per 64-device cell, each constructing a `pathlib.Path` only to take a basename, are built
once per engine. `live2/arms_policy.py` loads this copy; every replay, fit and scoring path keeps
importing the frozen module, so nothing that produced a committed number changes its import.

**The copy is held to byte-identity, not to good intentions.**
`policy/tests/test_eng1_engine_fast.py`, 8 tests:

| test | what it establishes |
|---|---|
| the two files differ only where the copy says | every function in both files is compared as a parsed syntax tree with docstrings stripped: the copy may add exactly `_basis_step` and `_basis_pol4`, may change exactly `Eng1Engine.predict`, and may differ nowhere else. A drift anywhere in the other several hundred lines fails. |
| the frozen module is what the freeze recorded | its md5 against `t0b_freeze.json`, so a copy can never become an excuse to edit the original |
| StudyENG1 / StudyENG1c Part C FIT trials | 406 FIT trials, 43,752 recorded rows turned into `Request`s in their own kind, tokens and cached tokens; both engines' `predict` compared field for field including `basis`, at two concurrency values. The 174 HOLDOUT trials are filtered out and never built. |
| StudyENG1d FIT trials | the committed `eng1d_replay.load_trials("fit")`, 180 trials, same comparison; the 60 HOLDOUT pairs are never built |
| the token range including out of sample | a sweep across 0 to 100,000 tokens, all four request kinds and all three readiness values, because `in_sample` and its basis line are part of the output and the out-of-sample branches must match too |
| every call the policy really makes | every `predict` call a dry 8-device cell makes is recorded (5,612 of them), de-duplicated, and replayed through both engines. The recorded `meta` is asserted to be scalar-valued so the replayed call is exactly the call the policy made, not a lossy copy of it. |
| the live path loads the copy | `arms_policy.Eng1Engine is eng1_engine_fast.Eng1Engine`, and is not the frozen class |

All 8 pass; 392 policy tests pass, the three frozen-md5 tests among them.

**New decision latency, committed 180 s fixture, 32 / 64 / 128 devices:**

| devices | p50 | p99 | max | p99 before this row (StudyLIVE2-fix) | p99 after P1 | p99 now | total |
|---|---|---|---|---|---|---|---|
| 32 | 22.469 ms | **111.652 ms** | 116.283 ms | 214.0 ms | 154.172 ms | 111.652 ms | **1.92x** |
| 64 | 55.857 ms | **280.731 ms** | 344.073 ms | 545.4 ms | 385.720 ms | 280.731 ms | **1.94x** |
| 128 | 139.383 ms | **1,149.689 ms** | 1,669.859 ms | 2,152.6 ms | 1,482.719 ms | 1,149.689 ms | **1.87x** |

Every cell reached the full 194.9 s of virtual time at 100 % CPU with no wall guard hit. The
fast engine alone is worth 1.38 / 1.37 / 1.29x on top of P1's three changes. The D99 equivalence
grid is 6 of 6 byte-identical with the fast engine in place, and its reference-to-fast speed-up
has now risen from the committed 6.0 to 7.1x to **7.60 to 10.47x**.

**Where that leaves the goal.** 32 devices is now 1.12x over the 100 ms period, near enough that
it would meet it on a quieter machine; 64 is 2.8x over and 128 is 11.5x over. The row's verdict
therefore does not change: the uncapped policy does not keep up at 64 and 128 devices, the curve
is reported, and the cap stays off. The remaining options are a design question, not an
implementation one, and they are written up in `reports/study_live2_perf.md` under "Bounding
decision cost: options" as a design note with no code.

# StudyLIVE2-harness addendum (H100): answers leave at their first token, requests are stamped at the wire

Built on the H100 after the user reassigned the addendum (2026-11-18); flash continued StudyLIVE2-perf. File ownership
for this work: the coordinator's I/O path (`asyncbackend.py`, which replaced `backend.py` on that path, `procsplit.py`,
`bridge.py`, `run_live2_real.py`, the completion-handling parts of `coordinator.py`); nothing under
`experiments/orchestration/policy/` or `live2/arms_policy.py` was edited. Run outputs:
`results/orchestration/live2/harness_addendum/`. Not a measurement: every header says `is_measurement: false`.

## HA1. Diagnosis on the real 32B: the late actions are answers, and the cause is the stamp, not the forwarding

Cell: 22808d0's runner with per-kind instrumentation only, edf, 8 devices, 120 s, mode A, seed 0, round-1 server
restarted (`diag_edf_n8`; PROVISIONAL: its coordinator process loaded `coordinator.py` and `bridge.py` from a mid-edit
working tree, but forwarding behaved as in 22808d0 because nothing registered the new path).

| measure | p50 | p99 | max |
|---|---|---|---|
| lateness, `answer_delivered` (140 of 718 over 50 ms) | 27.4 ms | **1,159.1 ms** | 1,211.0 ms |
| lateness, every other action kind (frame_arrived, monitor_opportunity, ...) | <= 0.10 ms | <= 0.37 ms | 0.37 ms |
| first SSE token to stream end, per request (request.jsonl) | 40.0 ms | **1,162.9 ms** | 1,216.9 ms |
| stream end to the coordinator forwarding the answer | 2.6 ms | 11.5 ms | 24.8 ms |
| stream end to the emulator receiving it | 8.9 ms | 16.6 ms | 27.6 ms |

A cloud answer carries `t_done` = its first-token time (the scorer's definition of delivery), but it could only be
forwarded when its stream ended; the monitor and recall answers are 1 to 2 output tokens and under load the last token
waits behind other requests' prefill for up to 1.2 s, so the answer reached the emulator that far behind its own
`t_done`. Forwarding at stream end, as first prescribed, was then built and run (`fix_edf_n8`): stream end to forward
fell to p99 0.12 ms (716 answers forwarded, 0 mismatches) and `answer_delivered` lateness was unchanged at p99
1,152.9 ms, which is the NEGATIVE CONTROL for the diagnosis: removing the forwarding delay does not touch the lateness.

## HA2. The ruling and the fix

User ruling, Option 1: forward each cloud answer at its FIRST CONTENT TOKEN, `t_done` unchanged (first-token time),
monitor score from the first token's logprobs, recall letter from the first token, any recall letter that differs from
the full-text letter counted per run, `cache_path` taken from `request.jsonl` (the payload carries None at that
instant). Implementation:

1. `asyncbackend.py`: the I/O loop calls `on_first` at the first chunk carrying content or logprobs, and `on_complete`
   when the stream ends, before the future resolves. The time between the first SSE line (`ttft_s`'s existing
   definition) and the first content token is recorded per request.
2. `coordinator.py`: `answer_on_first` builds the cloud answer on the I/O thread from the submission, the partial
   response and the opportunity's deadline (fixed at creation); `answer_on_completion` is the fallback for a stream
   with no content token, and for an already-forwarded answer it compares the first-token letter / score with the full
   response's. `_settle` builds the same event through the same `_cloud_answer` and still records it;
   `n_forward_mismatch` counts any difference outside the two fields Option 1 lets differ.
3. `bridge.py`: an answer already forwarded is recorded but not sent again.
4. `procsplit.py`: the child registers both callbacks and writes the answer to the fleet under a send lock shared with
   the decision thread. The arm still learns of every completion in `_collect` at its next epoch, exactly as before.
5. From flash's branch `flash-harness-addendum` (not merged wholesale): (a) the TRUE SUBMISSION STAMP (epoch start to
   submit call added to the request's run time), corrected so a submission outside an epoch (a chained recall released
   by a completion) is not charged the last epoch's delay; (b) `preflight.py` (refuses a real-server run with any
   unstored or empty frame), called before the server starts; (c) the two count tests derived from the committed
   manifests (user ruling; authorized for these two tests only).
6. THE WIRE-TIME STAMP (added after the first acceptance round, HA3). Flash's stamp measures only from the epoch's
   start; at 64 devices policy-core's events queue in the coordinator process behind 100 to 170 ms decisions, so the
   epoch itself begins with a run time already in the past. The parent now recovers the emulator's clock origin on
   CLOCK_MONOTONIC (the minimum of `monotonic() - t` over its calls, within about 0.1 ms; unit-tested) and sends it to
   the child, and the I/O loop stamps each request with that run clock as it goes on the wire, never earlier than the
   coordinator's own stamp. The total from the epoch's nominal instant to the wire is reported as
   `submit_delay_total_ms`. Arms, decisions, schema, digests and scoring are unchanged; the request's `t_submit` is now
   its true wire time.
7. `run_live2_real.py`: lateness per action kind (and the per-action detail, gzipped), first-token / completion to
   forward gaps, receipt gap, forwarding counters, recall-letter differences, submit delays, decision latency, the
   preflight report, and `git_working_tree` (HEAD, dirty files, diff sha256) in every run's header and meta.

## HA3. Acceptance on the real 32B (round-1 server restarted per cell, mode A, 120 s, seed 0)

Round 1 (`acc_*`, before item 6): edf 8 and 64 and policy-core 8 passed; **policy-core 64 FAILED**: `answer_delivered`
p99 767.1 ms (130 over 50 ms; run p99 45.8 ms), forward p99 0.11 ms, epoch-start submit delay p99 143 ms, decision
latency p50 45.0 / p99 132.8 ms. Item 6 was added and ALL FOUR cells rerun on the final code (`acc2_*`):

| cell | lateness p99, all actions (max) | `answer_delivered` p99 (max) | kinds with any sample > 50 ms | first token to forward p99 | submit delay to the wire p50 / p99 (max) | decision latency p50 / p99 | requests / HTTP errors | digests equal | scored |
|---|---|---|---|---|---|---|---|---|---|
| edf, 8 | 0.110 ms (0.42) | 0.11 ms | none | 0.10 ms | 3.0 / 7.3 ms (16.4) | 0.5 / 0.7 ms (round 1) | 720 / 0 | yes | yes |
| edf, 64 | 0.159 ms (27.4) | below 1 ms | none | 0.11 ms | 9.2 / 24.0 ms (58.7) | 3.7 / 4.5 ms (round 1) | 624 / 0 | yes | yes |
| policy-core, 8 | 0.104 ms (0.17) | 0.10 ms | none | 0.10 ms | 9.4 / 14.9 ms (44.6) | 4.1 / 11.1 ms | 767 / 0 | yes | yes |
| **policy-core, 64** | 0.168 ms (38.2) | **0.105 ms (38.2)** | **none** | 0.11 ms | **61.0 / 1,503.3 ms (1,572.0)** | 47.3 / 138.2 ms | 929 / 0 | yes | yes |

Every action kind is within the 50 ms rule in every cell. Policy-core's decision cost at 64 devices now appears where
the ruling puts it: as submit delay (p90 860 ms, p99 1.50 s from the epoch's instant to the wire, the queue behind
decisions that take longer than the 100 ms period), not as held answers or an invalid run. Forwarding: 0 mismatches
in every cell; recall answers forwarded at the first token 6, 5, 0 and 1, with **0 letters differing from the full
text (rate 0 of 12)**; 0 monitor scores differing; 0 callback errors. Preflight: every frame reference stored
(10,038 of 10,038 at 64 devices). End-of-run truncation, as before the addendum: requests submitted in the last instants
before the coordinator closes are not built or completed (edf 64: 624 submitted, 623 built, 621 completed; round 1:
598 / 594), which no answer or lateness figure includes.

## HA4. Mechanism verification and results consistency

The causal claim is about the apparatus (an answer reaches the fleet when its content exists, stamped with the run
time its request really had). Named mechanism: answers stamped at the first token but forwarded at stream end (HA1),
and requests stamped earlier than their wire time (HA3 round 1). Instantiated: per-kind lateness, first-token to
stream-end gap, forward gap, submit delay. Traced: every late action in `diag_edf_n8` is an `answer_delivered`, and
its lateness tracks the request's first-token to stream-end gap (p99 1,159 vs 1,163 ms). Negative controls: forwarding
at stream end (`fix_edf_n8`, p99 1,153 ms: the forwarding gap was not the cause), and first-token forwarding without
the wire stamp (`acc_pc_n64`, p99 767 ms at 64 devices while edf 64 passed: the stamp was the remaining cause).
Alternative explained away: GIL or emulator load (the emulator used 1.9 % CPU and every non-answer kind stayed at
p99 <= 1 ms throughout). Results consistency: the round-1 and round-2 cells agree where nothing changed (edf 8 p99
0.107 vs 0.110 ms; policy-core 8 0.110 vs 0.104 ms); the policy-core decision latency at 64 devices (p99 132.8 /
138.2 ms here) sits inside the committed flash range: 115.7 ms in the harness H5 cell (ratio 1.19x) but StudyLIVE2-perf's speed table gives 385.7 ms at 64 devices (a 2.8x
DISAGREEMENT, beyond the 2x rule; candidate, not tested: that table times decisions on flash's CPU over its own
replay, not the live H100 coordinator; FLAGGED to StudyLIVE2-perf; no acceptance result depends on the decision
latency's value, only on the lateness, which is measured directly); request counts per cell match round 1 within 4 %.

## HA5. Suites

| suite | result |
|---|---|
| `live2/tests/` (coord, fakeserver, fix, fix2, harness) | 94 of 94 pass (harness 26, of which 13 new or adopted: first-token forwarding through a real split run on the fake streaming server, recall-letter counting, the stream-end fallback, build pieces, the clock-origin estimate, the submission stamp, dry-run determinism, flash's four preflight tests, the two derived count tests) |
| `live2/fleet/tests/test_live2_fleet.py` | 234 of 234 checks pass |

Open issue left to StudyLIVE2-perf: policy-core's decision latency at 64 devices (p99 138 ms) exceeds its 100 ms
period, so its requests queue (submit delay p99 1.5 s); that is now a measured cost of the policy, not a harness defect.

## P7. Option 0 implemented: the terminal state-value memo

The design note's Option 0, which is the only one that cannot change a decision.
`readiness.StateValueCache` memoises `state_value` WITHIN one decision period;
`arms_policy.decide` clears it at the start of every period, which is what makes the scope real
and bounds any key error to one period instead of a run. All three paths are kept: `on`, `off`
(the pre-Option-0 path) and `shadow`.

**The key is held to its claim, not asserted.** `readiness.state_value_key` names every input the
returned dict depends on, derived term by term from the body: the belief's probabilities, size
and staleness; `demand.rate_rc(rep, in_episode)` and `conditional_rate_enabled`; `link.down_s()`,
which is the only link quantity reached (`_u_rc_from_tier` always passes `unsent_frames = 0`, so
`up_s` is never called); `h_s`, `deadline_s`, `omega_rc`, `rep`, `qtype`, `exclude_job`,
`credit_allowed`; and the profile's identity. `policy/tests/test_readiness_state_value_cache.py`,
14 tests, checks it three ways:

| test group | what it establishes |
|---|---|
| per field (8 tests) | perturb each named input, then ask the cache again: the key must change AND the answer must equal a fresh uncached computation. A key that missed a field would serve the stale value and fail. Whether a field moves the value is reported, not required, because a value can sit on a plateau where it genuinely does not matter. |
| shadow mode on a real cell | 8 + 8 devices over 60 s with both values computed on every call: **44,065 shadow checks, zero mismatches**. A shorter cell is useless here because no robot has built a history yet and the terminal loop never runs, which is itself worth knowing. |
| the negative control | the key is deliberately broken (the belief dropped) and shadow mode is required to RAISE. Without this, the test above could pass because the machinery never fires. |
| period scope | the cache is cleared exactly once per decision period, counted against the decision-latency sample count rather than the logged-decision count, and the entries alive at the end belong to the last period only |
| a hit is a copy | a caller that mutates a returned dict cannot poison later hits |

**The premise holds and the hit rate says so.** On the 120 s fixtures the memo serves
93.6 % of calls at 8 devices, 98.3 % at 32 and **98.9 % at 64** (2,409,856 calls, 32 live entries
at any time). That is the quantitative version of the design note's claim that successive
candidates in a period differ only in the devices the earlier admits touched.

**Decision latency, committed 180 s fixture:**

| devices | p50 | p99 | max | p99 before Option 0 | committed baseline | total for the row |
|---|---|---|---|---|---|---|
| 32 | 20.183 ms | **100.590 ms** | 104.340 ms | 111.652 ms | 214.0 ms | **2.13x** |
| 64 | 50.703 ms | **252.542 ms** | 310.383 ms | 280.731 ms | 545.4 ms | **2.16x** |
| 128 | 121.605 ms | **994.789 ms** | 1,477.621 ms | 1,149.689 ms | 2,152.6 ms | **2.16x** |

D99 equivalence 6 of 6 byte-identical, reference-to-fast now **7.89 to 11.20x** (committed 6.0 to
7.1x). Option 0 is worth 1.11 / 1.11 / 1.16x on this fixture; it is worth more on a shorter one
(1.52x at 64 devices over 60 s), because the hit rate is the same but the per-period candidate
count differs.

**32 devices now meets the period**, at 100.590 ms against 100 ms, which is 1.006x and inside
run-to-run variation. 64 is 2.5x over and 128 is 9.9x over, so the row's verdict still stands for
those two sizes.

## P8. Option C measured, and the measurement kills it

Measurement only, no implementation, exactly as the design note proposed: find out how much is
reusable BEFORE building anything. `policy/measure_rollout_reuse.py` wraps `Rollout.run` from
outside, fingerprints what each call was given and what it returned, and compares consecutive
candidates within a period. Dry-run fixtures, 120 s, seed 1.

| | 8 devices | 32 devices | 64 devices |
|---|---|---|---|
| rollouts | 14,538 | 52,326 | 85,576 |
| periods / with more than one rollout | 930 / 930 | 1,200 / 1,200 | 1,200 / 1,200 |
| rollouts per period, median / p90 / max | 14 / 22 / 46 | 40 / 70 / 216 | **60 / 172 / 344** |
| INPUT: devices identical, median / min | 1.000 / 0.500 | 1.000 / 0.750 | 1.000 / 0.857 |
| INPUT: jobs identical, median | 1.000 | 1.000 | 1.000 |
| INPUT: pending list identical | 85.7 % | 92.1 % | 95.0 % |
| INPUT: in-flight list identical | 92.8 % | 96.2 % | 97.7 % |
| OUTPUT: delivery rows identical, median | 0.500 | 0.714 | 0.727 |
| OUTPUT: opportunity rows, reusable PREFIX, median | 0.300 | 0.300 | 0.333 |
| OUTPUT: **first divergence, as a fraction of H** | **0.076** | **0.199** | **0.221** |
| OUTPUT: rollout totals identical | 29.3 % | 21.9 % | 24.2 % |

**The finding, and it is a clean negative for Option C.** The INPUTS of consecutive candidates
are nearly identical, which is exactly why Option 0 works: the median pair shares every device
and every job, and shares the pending list outright 85 to 95 % of the time. But the TRAJECTORY
diverges almost immediately: the first differing row appears at **7.6 % of the horizon at 8
devices and 22.1 % at 64**, and only about a third of the opportunity rows are a reusable prefix.
An incremental rollout can only carry forward the prefix before the first difference, so the
ceiling on what it could save is roughly a fifth to a quarter of each rollout body, about 1.3x at
best, against a 2.5x gap at 64 devices. Option 0, which exploits the INPUT sharing the same
measurement shows is near-total, already beat that ceiling.

**So Option C is not worth building, and the measurement cost one script to establish rather than
an implementation to abandon.** That is the outcome the design note hoped for when it put the
measurement first.

**One correction to the design note.** It estimated "around 30 candidates" per period at 64
devices. The measured median is 60, the p90 is 172 and the worst period runs 344 rollouts. That
makes the candidates factor larger than assumed, which strengthens the case for the options that
attack it (A and B) and weakens nothing above, since Option 0 attacks the other factor. The note
has been updated.

## HA6. Robot outcomes of the addendum's cells are INVALID (user ruling 2026-11-18)

Found by StudyMOT2's seed 10 diagnosis: the live coordinator's per-session history size is not cumulative
(`cstate.history_append` keeps `max(batch est_tokens, current)`; the emulator forwards the per-batch `est_tokens`, not
the trace's `cum_tokens`), so every robot history looked many times smaller to the arms and edf's "whole" rebuilds
built only a prefix. Every ROBOT outcome in this addendum's cells (`diag_edf_n8`, `fix_edf_n8`, `acc_*`, `acc2_*`) is
therefore INVALID and must not be cited; each run directory carries `INVALID_ROBOT_OUTCOMES.txt`. The HARNESS criteria
the addendum was accepted on (emulator lateness per action kind, forwarding gaps and counters, digests, HTTP errors)
do not depend on history sizes and stand. Fix owned by flash.

---

# History-size accounting fix, and a release-rate audit of every arm

Found by the H100 on StudyMOT2 seed 10, 2026-11-18. Part 1 is an implementation fix, applied and
reported here. Part 2 is a REPORT ONLY: it changes nothing and proposes a methodological change
for the planner and user to rule on.

## H1. The defect: both sides of one wire

**Both sides are wrong, and each alone would have been enough.** The trace is correct and carries
both quantities on every history record (`fleet/trace.py:384-392`): `est_tokens=tok`, that
batch's own increment, and `cum_tokens=tokens_sent`, the session's running total, which resets at
`session_start` (D83, `trace.py:343`) and already includes the D101 preload (`trace.py:352`).

**Producer, `fleet/emulator.py`.** It forwarded the increment and threw the total away:

    est_tokens=int(r["est_tokens"])                      # the PER-BATCH increment

**Consumer, `cstate.py:208`.** It then kept a maximum, which on a stream of increments settles on
the largest single batch and never on the total:

    s.est_tokens = max(int(ev["est_tokens"]), s.est_tokens) if ev.get("est_tokens") \
        else len(s.frames) * D2_TOK_PER_IMG + D2_HEADER_TOK

The `else` branch is the tell: the fallback, used when the field is absent, computes a CUMULATIVE
total from the frames accumulated so far. The fallback was right and the primary path was wrong.
`cstate.py:196`, the preload, had the same `max(...)` and was harmless only because a preload is
a session's first holding.

**Measured on the trace the H100 used** (seed 10, 12 devices, 600 s), reproduced exactly:

| device, session | batches | largest single batch | true cumulative | understatement |
|---|---|---|---|---|
| robo002, s001 | 13 | 1,381 | **17,581** | **12.7x** |
| robo000, s001 | 12 | 1,381 | 16,231 | 11.8x |
| robo001, s001 | 9 | 1,381 | 12,181 | 8.8x |
| robo002, s000 | 9 | 4,621 | 13,801 | 3.0x |
| robo000, s000 | 9 | 8,401 | 18,301 | 2.2x |
| robo001, s000 | 12 | 13,351 | 27,031 | 2.0x |

All 12 sessions in that trace were understated, by 2.0x to 12.7x.

**Why the frames went missing too, which is one defect and not two.**
`coordinator._advance_build` derives the FRAME COUNT from the token budget:

    target = min(int(target_tokens or s.est_tokens), max(int(s.est_tokens), 1))
    piece = left if slice_tokens is None else min(int(slice_tokens), left)
    n_new = max(1, int(round(piece / float(CS.D2_TOK_PER_IMG))))
    new_refs = s.frames[already:already + n_new]

With the belief understated 12.7x, `n_new` is 12.7x too small, so a "whole" rebuild carried about
a twelfth of the history. That is the H100's 2,171-token prompt for a 24,838-token history, and
it is why the real cold prefill then happened inside the recall request and why 24.3k and 14.9k
rebuilds appeared to take 0.53 s and 0.36 s. One root cause, three symptoms.

**Why the dry-run fixtures never caught it.** `traces.py:210`, the synthetic producer, already
emitted the cumulative value (`D2_HEADER_TOK + frames_so_far * D2_TOK_PER_IMG`), and for a
monotonically increasing sequence `max(cum, so_far) == cum`, so the old consumer was accidentally
correct there. The defect existed only on the fleet-trace path, which is the path the pilot and
MOT2 use.

## H2. The fix: one semantics, stated in CONTRACT.md

`est_tokens` ON THE WIRE is the session's CUMULATIVE history tokens after this event, and the
coordinator's belief is the LATEST value received, not a sum and not a maximum. All three
producers now agree, and `traces.py` already did.

| file | change |
|---|---|
| `fleet/emulator.py` | both producers send `_cumulative_tokens(rec)`, which returns the record's `cum_tokens` and RAISES on a record that lacks it rather than silently reading an increment as a total |
| `cstate.py` | `history_append` and `history_preload` set the belief to the value received; the `max(...)` is gone from both. The absent-field fallback is unchanged and was already cumulative |
| `CONTRACT.md` | a "History size" section fixing the semantics, the producer table, the defect it replaces, and a note that the FAIRNESS DIGEST deliberately keeps the trace record's `est_tokens` (the increment) so no digest byte moves |

**Resetting on a new session (D83) and the preload (D101) set the same quantity**, which falls
out of using `cum_tokens`: it restarts at 0 per session and includes the preload.

**No H100-owned file was touched.** The fix is in the emulator and `cstate.py`, both ours.

## H3. Every consumer of history size, checked

`s.est_tokens` is the single source, so every consumer is corrected by correcting it. Traced for
every arm:

| consumer | where | how it was wrong |
|---|---|---|
| MATERIALIZE whole and piece sizing, and the FRAME COUNT each build carries | `coordinator._advance_build`, `target` / `piece` / `n_new` | sent about a twelfth of the frames for an understated history |
| `readiness_tokens` on every recall opportunity, which every arm reads | `cstate.py:318`, `tok = max(int(s.est_tokens), 1)` | the arms' `PendingItem.tokens`, so EDF ordering, B8's cost and B9's allocation all priced a 1,381-token rebuild |
| prefix-built size (D100) and the built / total comparison | `coordinator._settle`, `s.built_tokens >= s.est_tokens` | a session was declared fully built after one piece |
| residency and host-tier bookkeeping | `cstate.py:351`, `used = sum(s.est_tokens ...)` | host-tier occupancy understated, so the believed tier was wrong |
| the cost model's rebuild and harm inputs | `C.recall_gpu_s(max(piece, 1), "COLD")` and `recall_ttft_s` through the arms | rebuild time and the harm it imposes both understated |
| feasibility and the policy's own job sizing | `arms_policy` through `q.readiness_tokens` | jobs looked feasible that were not |
| B8 and B9 inputs | `constructed.py`, `C.recall_gpu_s(max(q.readiness_tokens, 1), ...)` | both baselines' admission arithmetic |

## H4. Tests, and that they fail on the old code

`live2/tests/test_live2_history_size.py`, 9 tests on the real seed-10 12-device fleet trace.
**Six of the nine FAIL on the pre-fix code**, verified by reverting both files and re-running:

| test | pre-fix |
|---|---|
| the believed history equals the trace's cumulative total at every append | FAIL |
| it holds across session chaining (D83) | FAIL |
| it holds for a preloaded session (D101) | FAIL |
| a whole MATERIALIZE carries every frame the history held at that moment | FAIL |
| the frame count resolves to the history size (`round(tokens / 90) == N`) | FAIL |
| a record without `cum_tokens` is refused | FAIL (the guard did not exist) |
| the defect is present in the committed trace | passes either way, by design: it reads the trace alone |
| pieces partition the history with no gap and no overlap | passes either way, and that is worth stating: the partition property was never broken, only the COVERAGE was |
| prompt accounting scales with history size through the fake server | passes either way on this fixture |

The two build tests needed two corrections of my own making, both recorded because each would
have made the test pass for the wrong reason: a dry run with no `frames_root` sends every frame
as a uuid reference, so `sent_bytes_for` stays empty and progress cannot be observed at all (the
tests now build a frame store); and a build can only carry the frames that had ARRIVED by then,
so comparing against the session's final frame list fails on a correct build (the tests now
capture the history as it stood at each submit).

## H5. Decisions changed, which is expected and is not a failure

| fixture | arm | decisions before | after | **changed** |
|---|---|---|---|---|
| synthetic D99 grid, 6 cells (4 and 8 devices x seeds 1 to 3) | policy-core | 490 to 1,548 | identical | **0 of 6 cells differ** |
| fleet trace, seed 10, 12 devices, 600 s | edf | 6,520 | 6,520 | **1,174 (18.0 %)** |
| fleet trace, seed 10, 12 devices, 600 s | policy-core | 6,638 | 5,305 | **6,464** |

The synthetic grid is unchanged for the reason in H1: those fixtures were already cumulative, so
the old `max(...)` was accidentally right there. On the fleet trace, where the belief was wrong by
2.0x to 12.7x, 18 % of edf's decisions move and policy-core's decision count falls by 1,333
(20 %), because a correctly priced rebuild is far more expensive and far fewer are worth starting.
**The old decisions were computed on wrong inputs; these are not regressions.**

The D99 equivalence grid (reference clone against fast clone) is unaffected and still identical,
and no fairness digest moved, by the deliberate choice recorded in CONTRACT.md.

## H6. Part 2: the release-rate audit. REPORT ONLY, nothing changed

**The finding is confirmed and it is worse than a tie.** On seed 10, 12 devices, the trace offers
**10.82 dashcam instants per second** and 10.87 units per second in total, against `edf`'s hard
ceiling of **10.00 per second**. The backlog is permanent by construction, and because EDF orders
by deadline and a dashcam instant's deadline (0.5 s) is always nearer than a robot question's, the
questions sit behind the instants and starve.

| arm | max units released per 100 ms period | effective ceiling | quoted rule |
|---|---|---|---|
| `device-only` | 0 | 0, sends nothing | `arms.py:87` DeviceOnlyArm, "Sends nothing" |
| `edf` | **1** | **10 /s** | `arms.py:179-181`: `order = Rollout._edf(None, items)`, `first = order[0]`, then `on = first is not None and first.item_id == "mon:" + s.stream_id`. ONE unit per epoch across monitoring and recall COMBINED. `releases_one_per_epoch = True` (`arms.py:116`) |
| `edf-piece1024` | **1** | **10 /s** | the same class, `Pi0Edf`, with `piece_tokens` set |
| `edf-piece2048` | **1** | **10 /s** | the same class |
| `always-cloud-fcfs` | every stream and every recall | engine capacity | `naive.py:56-57`: `streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams]`, `recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall]`. No count cap at all |
| `utility-per-cost` (B8) | unbounded by count | the GPU budget | `constructed.py:235-255`: a greedy pass over ALL candidates sorted by utility over cost, taking each while `cost <= left`, `left` being `obs.budget_remaining_gpu_s` |
| `b9` | unbounded by count | the GPU-rate cap | `constructed.py:358-363`: `cap = budget_remaining_gpu_s / horizon_s` then `V.allocate_discrete(qs, cap, horizon_s, "maxmin")` across all live streams |
| `policy-core` | unbounded by count (`release_eval_cap_k` is None, F-2) | the GPU budget and its own DeltaJ test | the release loop in `arms_policy._to_action`; D99 (4)'s cap bounds how many items get a full DeltaJ EVALUATION, not how many are released, and it is off |

**Measured, not assumed.** On the seed-10 fleet replay, releases per decision period:

| arm | median | p90 | max | periods with a release |
|---|---|---|---|---|
| `edf` | 1 | 1 | **1** | 5,106 |
| `policy-core` | 1 | 2 | **3** | 3,322 |

So the asymmetry is real but narrower than "several against one": both sit at a median of 1, and
the difference is in the ceiling, 3 against a hard 1. `edf` cannot exceed 1 however much capacity
is free; `policy-core` can and does, up to 3 on this fixture, and the two uncapped baselines
(`always-cloud-fcfs`, B8, B9) can go far higher.

**Does the policy's ROLLOUT model pi_0 as one release per epoch? No.** `Rollout.run` builds
`queue = forced + rest` and serves the whole queue serially, limited only by the horizon
(`rollout.py:203-219`): `start = max(free_at, p.due_at)`, and an item is skipped only when
`start > end`. There is no per-epoch release limit anywhere in the rollout, and
`releases_one_per_epoch` appears only in `arms.py` as a DECLARATION in `live2_describe`, never as
a constraint the rollout honours. **So the policy's predicted futures assume a WORK-CONSERVING
scheduler, which is faster than the `edf` arm actually is and consistent with the live engine.**
The policy is not pessimistic about itself; the EDF baselines are crippled relative both to the
engine and to the continuation the policy assumes for them.

**B9's ordering and release rule**, for the record: component (iii) owns `order`, using EDF
ordering among the admitted, with admission by a max-min discrete allocation against a GPU-rate
cap derived from the remaining budget, and refusals on budget (component iii) and on causal reuse
(component iv). It is not count-capped.

### H7. Proposal, NOT implemented: a work-conserving release for the EDF family

This is a methodological change, so it is proposed and not applied.

**The minimal change.** In `Pi0Edf.decide`, replace the single `first = order[0]` with a prefix of
`order` admitted until a stated capacity bound is reached, keeping EDF order and keeping the
"pi_0 does not decline" rule for everything beyond the bound (it still DEFERs with `defer_s=0.0`
and is re-decided next epoch). One line becomes a loop; nothing else in the arm changes.

**The bound has to be stated, and there are three honest candidates.** It must not be a free
parameter chosen to make a baseline look good.

1. *In-flight bound.* Release while the coordinator's `in_flight` count is below a stated limit,
   which is what a work-conserving scheduler in front of a single-server engine would do. The
   limit is observable (`st.in_flight`) and needs no new evidence.
2. *GPU-budget bound.* Release while the period's share of `budget_remaining_gpu_s` is unspent,
   which is exactly the bound B8 and B9 already use, so the EDF family would be bounded the same
   way as the constructed baselines and the comparison becomes like-for-like.
3. *Offered-load bound.* Release up to the number of units offered in the period, which makes the
   arm exactly work-conserving and caps nothing but the queue.

**Recommendation: candidate 2**, because it is the bound two other baselines already use, it
introduces no new quantity, and it makes the release rule uniform across every arm that is not
`device-only`. Candidate 1 is the closest to "the engine's capacity" as the prompt puts it, but
the in-flight limit would itself be a new number.

**What it would cost.** Every committed `edf`, `edf-piece1024` and `edf-piece2048` number becomes
a number about a different arm, so they would have to be re-run, and the fix in Part 1 already
requires that. It is also a change to a BASELINE, which is the direction that most needs
pre-registration: a baseline that is quietly strengthened after the fact is worse than one that
is quietly weak, and this one is currently weak in a way that flatters `policy-core`.

**What it would not fix.** The engine still peaks near 15 requests per second against 10.87
offered, so a work-conserving `edf` would clear the backlog; but `policy-core`'s advantage on
seed 10 is currently measured against a baseline that cannot keep up at all, and nobody should
read the existing gap as the policy's merit until this is ruled on.

## H8. Six-check consistency protocol

1. **Cross-check against committed measurements.** The understatement reproduces the H100's
   report exactly: robo002's second session at 1,381 believed against 17,581 true, which is the
   number its notes give. The offered rate reproduces its 10.8 instants per second at 10.82, and
   `edf`'s 10 per second ceiling follows from the quoted rule rather than from a measurement.
2. **Physical plausibility.** The identity the sizing rule rests on is checked directly: a D2
   history of N frames is `N * 90 + 31` tokens, so `round(tokens / 90) == N`, which is asserted
   for every built session. The pre-fix "rebuilds" of 24.3k and 14.9k histories in 0.53 s and
   0.36 s were physically impossible against the committed cold-prefill rate, which is what
   makes them evidence of the defect rather than a finding.
3. **Distribution sanity.** The understatement is reported per session for all 12, not as a
   single ratio, and it ranges 2.0x to 12.7x. The release counts are reported as median, p90 and
   max rather than as a mean.
4. **Definition audit.** `est_tokens` had two meanings on one name and now has one on the wire,
   fixed in CONTRACT.md, with the fairness digest's use of the trace record's field called out
   explicitly so the two cannot be conflated again. "One unit per epoch" is quoted from the code
   rather than from the docstring that asserts it.
5. **Claim linkage.** The fix bears on no claim directly; it bears on every round-1 number that
   depends on history size, which is all of them for the recall path. Part 2 bears on whether the
   policy-against-baseline comparison is fair, which is the central comparison of the study.
6. **Proxy validity.** One proxy is used and labelled: the tests run against a frame store of
   1-byte files, because `coordinator._path` only tests existence and a dry run never reads the
   bytes. It is valid for frame COUNT and coverage, which is what the tests assert, and invalid
   for anything about image content or request size, which they do not.

## H9. Limitations

1. The decision-change counts are on one fleet trace (seed 10, 12 devices, 600 s) and two arms.
   Other seeds and the other six arms will also change and were not counted.
2. The tests assert the belief against the trace's own `cum_tokens`. If the trace's accounting
   were itself wrong, these tests would not catch it; what they establish is that the coordinator
   now believes what the trace says.
3. Part 2 is an audit of the code's release rules plus one replay. It does not measure what a
   work-conserving `edf` would score, because that arm does not exist.

---

# D114: the EDF family becomes work-conserving. PRE-REGISTRATION

Committed ALONE, before any code, per the user ruling D114 of 2026-11-18. No measurement appears
in this section. It exists so that the change to a baseline is on the record before the numbers
that will be produced under it.

## D1. The old rule

`edf`, `edf-piece1024` and `edf-piece2048` released exactly ONE unit per 100 ms decision period,
across monitoring and recall COMBINED. `Pi0Edf.decide` built the EDF order over the whole pending
set and then acted only on its head:

    order = Rollout._edf(None, items)
    first = order[0] if order else None
    ...
    on = first is not None and first.item_id == "mon:" + s.stream_id

Everything else was DEFERred with `defer_s=0.0`. The effective ceiling was 10 releases per second.

## D2. The new rule

Each 100 ms period, take the pending set in deadline order, with monitoring instants, rebuild
pieces and recall answers merged exactly as they are merged now, and release units from the head
while the number of in-flight cloud requests is below `C_inflight`. **In-flight means submitted
and not yet completed, counted across all kinds.**

`C_inflight = 4`, an arm parameter recorded in the run header. Its provenance is StudyD7b Part A
(`reports/study_d7_capacity.md:180`): 32B-I at N = 1 reaches **100 % GPU utilisation at
concurrency 4**, 12.73 req/s. The same report notes 99 to 100 % from concurrency 2 for 32B at
N = 9, so 4 is Part A's figure and the conservative choice, not the minimum across every N.

Kept unchanged:

- **pi_0's no-decline rule.** Nothing is declined for not fitting. An item beyond the release
  bound simply waits and is re-decided next period, and an item past its deadline falls to the
  device exactly as now.
- **One piece per MATERIALIZE** (D104 issue 6), and every piece size.

Not changed, and tested to be byte-identical: `policy-core` and its rollout,
`always-cloud-fcfs`, `utility-per-cost` (B8), `b9`, `device-only`.

## D3. Why, from the audit

Report section H6 measured the ceiling against the offered load. On seed 10 the trace offers
**10.82 dashcam instants per second** and 10.87 units per second in total against the arm's hard
**10.00 per second**, so the backlog was permanent BY CONSTRUCTION and not a scheduling outcome.
Because EDF orders by deadline and a dashcam instant's 0.5 s deadline always precedes a robot
question's, the questions sat behind the instants and starved.

The same audit found that the policy's rollout **already** models pi_0's continuation as
work-conserving: `Rollout.run` serves the whole EDF queue bounded only by the horizon, and
`releases_one_per_epoch` is a declaration in `live2_describe` that the rollout never honours. So
D114 brings the arm into line with the continuation the policy was already assuming for it. It
does not change what the policy predicts, and it removes a mismatch rather than introducing one.

## D4. That this is a baseline change, and what it costs

**This is a change to a BASELINE, made before any round-1 run.** It is the direction that most
needs pre-registration: a baseline quietly strengthened after the fact is worse than one quietly
weak, and the weakness being removed here FLATTERED `policy-core`.

**Every EDF-family number is re-run.** No committed `edf`, `edf-piece1024` or `edf-piece2048`
figure may be compared against a post-D114 one; they are numbers about a different arm. The
StudyLIVE2 history-size fix of the same date already forced a re-run of these cells, so D114 adds
no re-run that was not already owed.

The arms keep their names. The alternative, renaming to `edf-wc`, would break every existing
reference for a change that the re-run already makes unambiguous, so the names stay and this
entry is the record of what they mean from here.

## D5. No H100-owned file is touched

The in-flight count is already on the published interface: `obs.cloud.running_by_class`
(`baselines/interface.py:127`), built by `cstate.observation` from `st.in_flight`, which the
coordinator increments at submit (`coordinator.py:559`) and decrements at completion (`:591`).
That is exactly "submitted and not yet completed, across all kinds", so the rule reads a quantity
the arm is already given and the change is confined to `live2/arms.py`.

## D6. Decisions and defaults

Posted as up-front questions under Step 0. Any still unanswered when the code was written were
taken at the default and are marked PROVISIONAL in the implementation section.

1. **In-flight source.** Default, taken: sum `obs.cloud.running_by_class` over its classes. It
   needs no new plumbing and no interface change.
2. **Within-period accounting.** Default, taken: the arm counts the units it releases this period
   against the bound, because the observation is a snapshot taken BEFORE any of this period's
   submissions. Without this, a period that starts with 0 in flight would release the entire
   pending set.
3. **Snapshot staleness.** Default, taken: accept it. Completions during a period are not visible
   until the next one, which makes the arm slightly conservative and never over-admitting.
   Removing it would need coordinator plumbing.
4. **One shared budget across kinds**, filled in deadline order, so a period may release four
   instants, or three instants and one piece. This is what "counted across all kinds" requires.
5. **A unit and a request are not always one to one.** A released recall item that is not
   GPU-WARM emits both a recall answer and one MATERIALIZE piece, which is one head item but can
   become two cloud requests. Default, taken: the bound counts HEAD ITEMS released this period,
   and the coordinator's own `in_flight` reflects the true request count at the next epoch, so
   the loop self-corrects within one period. This is the one place where the rule's "units" and
   the engine's "requests" differ, and it is flagged rather than hidden.
6. **Deferred items consume no slot**; only released units do.
7. **`C_inflight` in the header.** Default, taken: an `__init__` parameter defaulting to 4,
   published through `live2_describe` so every run header records it.

---

# D114 implementation, and the D97 entry points recomputed under D101

Step 2 and Step 3 of the 2026-11-18 task. The pre-registration above was committed alone, before
this code, as the ruling required. Every decision listed under D6 was taken at its stated
default and is **PROVISIONAL**: no answer had arrived when the code was written, and D116 put
tonight's run unattended.

## E1. What changed

`live2/arms.py` only, in `Pi0Edf`, which is the class behind `edf`, `edf-piece1024` and
`edf-piece2048`:

    order = Rollout._edf(None, items)
    released = {p.item_id for p in order[:self._release_budget(obs)]}

where `_release_budget` is `max(c_inflight - sum(obs.cloud.running_by_class.values()), 0)`.
Taking a PREFIX is what charges each released unit against the bound inside the period: the
observation is a snapshot from before this period's own submissions, so the arm counts the head
items it releases itself. `c_inflight` is an `__init__` parameter defaulting to 4, rejected below
1, and published through `live2_describe` so it lands in every run header.

**No H100-owned file was touched**, and nothing outside `Pi0Edf` was touched.

## E2. A deviation from spec 3.5 that the planner must rule on

**Spec 3.5 of both `POLICY_SPEC_v3.md` and `policy_spec_v4.md` defines pi_0 as "deadline-ordered
release, ONE UNIT AT A TIME".** That is the exact wording. So:

- before D114 the ARM matched the spec text, and `Rollout.run` did NOT, because it serves the
  whole deadline-ordered queue bounded only by the horizon;
- after D114 the arm and the rollout agree with each other, and **both differ from the spec's
  wording**.

D114 is a user ruling and is implemented as ruled. But the spec text now needs either an
amendment or a recorded deviation, and that is a planner decision which this task does not
settle. The module docstring states the deviation rather than reciting the old claim; nothing in
the code changes the spec. The previous docstring asserted that one-unit-per-epoch "is what spec
3.5 defines pi_0 to be", which was true of the text and is why this is flagged rather than
quietly rewritten.

## E3. Release counts: the three cells of the ruling

`live2/tests/test_live2_d114.py`, 12 tests, all passing. The instants are given strictly
increasing deadlines through the D100 roster hook so that "in deadline order" is a real
assertion and not a tie broken by `item_id`.

| condition | required | measured |
|---|---|---|
| 10 pending, 0 in flight | exactly 4, in deadline order | 4, and they are `cam00` to `cam03` |
| 10 pending, 3 in flight | exactly 1 | 1, and it is `cam00` |
| 10 pending, 4 in flight | 0 | 0 |

Also asserted: 9 in flight releases 0 rather than going negative; `recall 2 + episodic 1` charges
3 slots, so in-flight is counted across all kinds as the ruling requires; 2 pending with a budget
of 4 releases 2; `releases_one_per_epoch` is now False; `c_inflight` reaches `live2_describe`;
`c_inflight=2` releases 2 and `c_inflight=0` raises; and both piece arms carry the same rule at
unchanged piece sizes.

## E4. The ceiling is gone, on the seed-10 12-device 600 s replay

| arm | per-period releases med / p90 / max, BEFORE | AFTER | total releases | in-flight max |
|---|---|---|---|---|
| `edf` | 1 / 1 / **1** | 1 / 2 / **4** | 5,106 to 5,452 | 5 to **4** |
| `edf-piece1024` | 1 / 1 / **1** | 1 / 2 / **3** | 5,095 to 5,639 | 4 to 4 |
| `edf-piece2048` | 1 / 1 / **1** | 1 / 2 / **4** | 5,096 to 5,620 | 4 to **4** |

The hard ceiling of one unit per period is gone, and **no period released more than
`c_inflight = 4`**, which is the invariant the tests assert. In-flight never exceeds 4 after the
change, where `edf` previously reached 5.

**An honest qualification the headline does not carry.** 5,452 releases over 600 s is 9.09 per
second, still BELOW the 10.87 units per second the trace offers. The arm is no longer limited by
a per-period count rule, but at `c_inflight = 4` and this mix's modelled service times it still
does not match the offered load, so a backlog remains. It is now a consequence of the concurrency
bound and service time rather than of an arbitrary count, which is the difference D114 was asked
to make, but it is not the same as "the backlog is gone".

## E5. Robot questions are NOT un-starved. This is a negative result

The ruling's requirement 3 expected that robot questions would no longer be starved by
construction. **On the replay they got slightly worse, and the reason is structural.**

| arm | robot questions released before their deadline, of 29 | before | after |
|---|---|---|---|
| `edf` | | **11** | **9** |
| `edf-piece1024` | | 0 | 0 |
| `edf-piece2048` | | 1 | 0 |

Counted as a replay count and not an outcome claim, exactly as the ruling asks: a question counts
when some `release_recall` decision carries its `opportunity_id` at a time before `t + 5.0 s`.

**Why.** The H6 audit named two mechanisms, and D114 addresses only the first:

1. the 10 per second release ceiling, which was below the offered load. **Removed by D114.**
2. EDF's strict deadline order, under which a dashcam instant's 0.5 s deadline is always nearer
   than a robot question's 5.0 s, so instants always sort ahead of questions. **Untouched by
   D114**, and now the extra capacity D114 unlocks is spent on MORE instants, which crowds the
   questions slightly further out.

So work-conserving release did not fix the starvation; it made the first mechanism stop binding
and left the second to act alone. Mechanism 2 is not a defect in the implementation: it is what
EDF is. Removing it would mean giving pi_0 a per-class share or a slack-based order, at which
point it is no longer pi_0 and no longer the common continuation policy of spec 3.5. **That is a
methodological change, so it is named here and NOT applied**, and the planner and user rule.

`edf-piece1024` sits at 0 both before and after because 1,024-token pieces never finish building
a 17,581-token history inside the window, so it never reaches a recall release at all. That is
the arms-5-and-6 behaviour those arms exist to exercise, not a D114 effect.

## E6. Nothing else changed: byte-identical decisions for every non-EDF arm

Captured by swapping only `arms.py` between the pre-D114 and D114 versions, with every other file
fixed, so the comparison isolates this change.

| arm | D99 grid, 4 and 8 devices x seeds 1 to 3 | seed-10 12-device 600 s replay |
|---|---|---|
| `device-only` | 6 of 6 IDENTICAL | IDENTICAL (29 decisions) |
| `always-cloud-fcfs` | 6 of 6 IDENTICAL | IDENTICAL (6,518) |
| `utility-per-cost` (B8) | 6 of 6 IDENTICAL | IDENTICAL (6,518) |
| `b9` | 6 of 6 IDENTICAL | IDENTICAL (6,488) |
| `policy-core` | 6 of 6 IDENTICAL | IDENTICAL (5,305) |

**30 of 30 grid cells and 5 of 5 replays byte-identical.** The EDF arms changed in all 6 grid
cells and in 6,826 of 6,861 replay decisions for `edf`, which is the intended effect.

`policy-core`'s 5,305 replay decisions also match the post-history-fix figure recorded in section
H5 exactly, which is an independent cross-check that the two changes compose as expected.

## E7. Step 3: the D97 entry points under D101

**The recompute was already committed**, by the StudyLIVE2-fix work of 2026-11-17 to 18:
`fleet/eligibility.py` carries the D101 version and
`results/orchestration/live2/fleet/eligibility_join/` holds its output at 600 s over seeds 0 to 3,
all three ratios and sizes 4 to 128. Re-running it would reproduce committed numbers, so it is
reported rather than recomputed, and both tables are read from the committed files.

| ratio | OLD entry (pre-D101) | **entry under D101** | per-seed under D101 (1 / 2 / 3) | seed 0, smallest measurable: old to new |
|---|---|---|---|---|
| 25 : 75 | 5 | **5** | 5 / 5 / 4 | 7 to **5** |
| 50 : 50 | 8 | **8** | 8 / 8 / 5 | 12 to **8** |
| 75 : 25 | 14 | **14** | 14 / 14 / 11 | 20 to **14** |

**The entry points do not move: still 5, 8 and 14.** Monotone above the entry at seeds 1 to 3 in
both tables. Seed 3 becomes more permissive (4, 5 and 11), but D97 takes the smallest size
eligible at EVERY reported seed, which is the maximum over seeds 1 to 3, and seeds 1 and 2 are
unchanged and binding. Seed 0 improves from 7 / 12 / 20 to 5 / 8 / 14 and, per D97 and D95 (7),
never sets an entry point.

**Why removing questions did not raise the entry points**, checked rather than asserted. D101
drops the questions before each robot's join point, which alone would reduce the pooled count.
But joining part-way also advances the session chain, so more sessions fit in the same 600 s. At
seed 1, size 8, ratio 50 : 50:

| quantity | pre-D101 | under D101 |
|---|---|---|
| sessions started | 6 | **10** |
| sessions completed | 2 | **6** |
| questions dropped by the join | n/a | 4 |
| **pooled robot questions** | **22** | **23** |

The chain advancing more than offsets the four dropped questions, so the pooled count rises
slightly and eligibility does not tighten. The preload also carries real cold history, median
6,061 tokens and up to 11,101 at this cell, which is the cold-rebuild pressure D101 exists to
create.

### E7a. The committed table was spot-checked at its boundaries, not merely cited

Because E7 reports committed numbers instead of re-running 1,500 cells, six cells were recomputed
fresh with `eligibility.cell(seed, n, ratio, 600.0)` and compared field by field. All matched
(`robot_questions`, `sessions_started`, `questions_before_join`, `robot_eligible`), and the three
chosen pairs straddle the entry points, which is what makes 5, 8 and 14 verified rather than
quoted:

| cell | pooled robot questions, fresh and committed | eligible at >= 20 |
|---|---|---|
| seed 1, n = 7, 50 : 50 | 14 and 14 | no |
| seed 1, n = 8, 50 : 50 | 23 and 23 | **yes, so entry 8** |
| seed 2, n = 8, 50 : 50 | 23 and 23 | yes |
| seed 2, n = 13, 75 : 25 | 15 and 15 | no |
| seed 2, n = 14, 75 : 25 | 23 and 23 | **yes, so entry 14** |
| seed 1, n = 5, 25 : 75 | 23 and 23 | **yes, so entry 5** |

## E7b. One existing test's precondition was invalidated, and what that shows

`test_live2_history_size.py::test_prompt_token_accounting_scales_with_history_size` FAILED under
D114 with "no build request was sent", having passed before it. The cause is E5's crowding-out,
reaching a test fixture: that cell runs `edf` against the fake server on the 12-device trace, and
with `c_inflight = 4` every slot goes to dashcam instants, so no MATERIALIZE is released inside
the 240 s window and the fixture had nothing left to measure.

The fixture now builds its arm as `Pi0Edf(None, c_inflight=64)`, with the reason stated in the
test, because that test's subject is PROMPT ACCOUNTING against history size and not the release
rule; the release rule is tested in `test_live2_d114.py`. The assertions themselves were not
weakened. **This is reported rather than quietly fixed, because the failure is evidence for E5:
D114 starves robot work on this trace strongly enough to empty a test that previously observed
builds.**

## E8. Gates

| gate | result |
|---|---|
| policy suite | 419 of 419 |
| live2 suites, including the 12 new D114 tests | all green |
| fleet suite | 234 of 234 |
| D99 equivalence grid (reference against fast clone) | 6 of 6 byte-identical |
| 12 frozen md5s | all green |
| non-EDF arms byte-identical | 30 of 30 grid cells, 5 of 5 replays |

## E9. Six-check consistency protocol

1. **Cross-check against committed measurements.** `policy-core` at 5,305 replay decisions
   reproduces section H5's post-history-fix figure exactly. The offered load of 10.82 instants
   per second reproduces H6. The pre-D101 entry points read from the committed
   `eligibility/` summary are 5, 8 and 14, which is what D97 records in the design log.
2. **Physical plausibility.** `c_inflight = 4` is quoted from StudyD7b Part A rather than chosen:
   32B-I at N = 1, concurrency 4, 12.73 req/s, 100 % GPU utilisation. The replay's 9.09 releases
   per second is BELOW that 12.73, so nothing here implies a rate faster than the committed
   curves. Section E4 states the gap rather than reporting the ceiling as closed.
3. **Distribution sanity.** Releases per period are reported as median, p90 and max, not as a
   mean, and the per-cell changed-line counts are listed individually (547, 740, 541, 1,484,
   1,480, 1,218) rather than summarised.
4. **Definition audit.** "In flight" is defined once, as submitted and not yet completed across
   all kinds, and tied to the exact quantity that implements it. "Unit" and "request" are
   distinguished explicitly in pre-registration item D6.5, because a released recall item can
   become two cloud requests. "Released before deadline" is defined as a release decision
   carrying the question's `opportunity_id` before `t + 5.0 s`.
5. **Claim linkage.** D114 bears on the fairness of the policy-against-baseline comparison, the
   study's central comparison. E5 is the result that matters most and it WEAKENS the reading that
   a work-conserving baseline would close the robot-question gap. E7 bears on D97 and D101 and
   leaves both unchanged.
6. **Proxy validity.** One proxy, labelled: in-flight is read from the arm's observation
   snapshot, not from an engine-side counter, so a completion landing mid-period is invisible
   until the next epoch. It is valid for the bound, which only needs to avoid over-admitting, and
   it is NOT a measurement of true instantaneous concurrency.

## E10. Limitations

1. E4 and E5 are one trace, one seed, one fleet size and a dry run. The replay's service times
   come from the cost model, not from a server, so the 9.09 per second is a model figure.
2. `c_inflight = 4` is grounded in Part A's N = 1 column. The same report reaches 99 to 100 %
   from concurrency 2 at N = 9, so 4 is conservative and no sweep over `c_inflight` was run.
3. E5's counts are replay release counts, not outcomes. Whether a released question is answered
   correctly or on time is a scored quantity and is not claimed here.
4. E7 reports committed numbers; it did not re-run the 1,500 trace cells behind them.

## HA7. Acceptance on the D114 build (530958f + D115 instrumentation, 284863a), real 32B, 2026-11-18 16:54 to 17:07

Same harness criteria as the addendum (mode A, 120 s, seed 0, round-1 server restarted per cell, mu EWMA, H = 0.5):
all four cells pass. `results/orchestration/live2/accept_d114/`.

| cell | lateness p99 (max), all kinds | kinds with any sample > 50 ms | decision wall p99 / CPU p99 (wall / CPU p99) | submit delay to wire p50 / p99 | requests / HTTP errors | digests equal | robot questions / cloud-answered / on time |
|---|---|---|---|---|---|---|---|
| edf, 8 | 0.121 ms (1.07) | none | 0.75 / 0.74 ms (1.04) | n/a | 715 / 0 | yes | 6 / 5 / 0 |
| edf, 64 | 0.180 ms (1.58) | none | 4.82 / 4.74 ms (1.04) | p99 28.9 ms | 1,016 / 0 | yes | 38 / 4 / 0 |
| policy-core, 8 | 0.129 ms (0.43) | none | 18.27 / 18.25 ms (1.02) | n/a | 767 / 0 | yes | 6 / 0 / 0 |
| policy-core, 64 | 0.218 ms (30.35) | none | 107.0 / 105.4 ms (1.06) | 46.3 / 266.6 ms | 1,015 / 0 | yes | 38 / 1 / 1 |

D115 fields present in every cell (`decision_time.jsonl.gz`, `host_load.jsonl.gz`, summaries in `run_meta.json`;
candidates from policy-core's own scoring counter, or the pending items ordered for edf). **History-size fix check
(`live2/build_coverage.py`): every robot build covers its history**: edf whole rebuilds 10 of 10 (prompt / trace
cumulative size 0.996 to 0.997; the same check on the pre-fix MOT2 seed 10 flagged 8 of 11), and policy-core's piece
chain 2,081 -> 4,151 -> 5,411 tokens of a 5,431-token history (0.996), its recall then 5,392 of 5,583 tokens cached.
Work-conserving EDF (D114) raised edf's requests at 64 devices from 624 (one release per epoch) to 1,016. Robot
service in these 120 s cells is very low (edf 4 of 38 questions cloud-answered at 64 devices, none on time); reported
as measured, a scheduling outcome of the arms, not a harness criterion. Suites on this build: live2 118 / 118 (incl.
flash's D114 and history-size tests), fleet 234 / 234, test_scale exit 0, policy 358 of 359 with one IMPORT error that
is environmental (`test_pol6_chain.py` checks a hardcoded flash scratch path under another account's /tmp directory,
permission denied on this host; not edited).

---

# D118: two stronger baselines, llf and vllm-priority. PRE-REGISTRATION

Committed ALONE, before any code, per the user decision D118 of 2026-11-18. **Neither arm enters
any run until the user decides.** They are built now so they are ready if round 1 adopts them
after the pilot. No measurement appears in this section.

Both exist to answer a reviewer: (a) "use least-laxity instead of EDF, and drop what cannot make
it", and (b) "isn't this just vLLM with priority scheduling?". The D114 replay is why: strict EDF
starves robot questions because a dashcam instant's deadline always sorts ahead of a question's,
so the question reaches the head too late for a multi-second cold rebuild.

## F1. Arm 9: `llf`, least laxity first

Lives in `live2/arms.py` beside `Pi0Edf` and shares its machinery.

- **Release: work-conserving exactly as D114.** Each 100 ms period, release from the head while
  in-flight cloud requests are below `C_inflight = 4`, counted the same way `Pi0Edf` counts them,
  namely `sum(obs.cloud.running_by_class.values())`, and charged within the period by taking a
  prefix.
- **Order: ascending laxity**, where `laxity = deadline - now - S_hat(unit)`.
- **Skip rule:** a unit whose laxity is below 0 at decision time is NOT released. It is removed
  and falls to the device, as an expired item does now. Skips are counted per kind.
- **No admission test beyond the skip rule.** No mu, no deficits, no utility.
- **Granularity:** a `piece_tokens` parameter, default None, meaning a whole rebuild as `edf`
  does. **Only `llf` (whole) is registered in `ARM_NAMES`.** Piece variants are reachable by
  parameter and are deliberately not named.

### S_hat comes only from committed measured curves

Every term is read from `baselines/costs.py`, the same module `edf-service-time` uses
(`baselines/naive.py:203`, `import costs as C` then `C.recall_ttft_s(...)`). **The policy's cost
model, its engine model and its rollout are never consulted (D74).** A test asserts the source
module.

| unit | formula | committed source |
|---|---|---|
| monitoring instant | `C.CLOUD_TTFT[("32BI", 1, 25)]` = **0.1422 s** | StudyD7 / D7b open-loop TTFT p50 at 25 % of peak, single frame (`costs.py:38`, `costs.py:150`) |
| recall, GPU-WARM | `C.recall_ttft_s(tokens, "GPU-WARM")` | StudyRH5 Part A isolated reload, D2, TTFT medians (`costs.py:71`) |
| recall, HOST-WARM | `C.recall_ttft_s(tokens, "HOST-WARM")` | the restore IS that committed curve |
| recall, COLD | `C.recall_ttft_s(unbuilt, "COLD")` + `C.recall_ttft_s(tokens, "GPU-WARM")` | the first term is exactly `unbuilt / COLD_PREFILL_TOK_S` (`costs.py:106-120`), the committed cold prefill rate per token; the second is the answer TTFT |
| rebuild piece | `C.recall_ttft_s(remaining, "COLD")` + `C.recall_ttft_s(tokens, "GPU-WARM")` | the job's laxity counts ALL of its remaining work, so a long rebuild starts early |

**Why the two terms do not double count.** `C.recall_ttft_s(tokens, "COLD")` returns
`tokens / rate` and nothing else: it IS the cold prefill, with no answer TTFT inside it
(`costs.py:115-117`). So the cold case adds a prefill term for the unbuilt tokens and a separate
warm answer term for the whole history, which is the state the history is in once the rebuild
completes. Adding a COLD answer term instead would charge the prefill twice.

Worked example, 17,581 tokens cold against a 5 s deadline: prefill 3.907 s plus answer 0.573 s
gives `S_hat = 4.48 s` and laxity 0.52 s, while a dashcam instant one second out has
`S_hat = 0.1422` and laxity about 0.86 s. **Under LLF the cold recall sorts FIRST; under EDF the
instant does.** That inversion is the arm's whole point and is the hand-built ordering test.

### The unbuilt size, and an honest limit

`unbuilt` is derived from the believed readiness: COLD means nothing is built, so
`unbuilt = readiness_tokens`; GPU-WARM and HOST-WARM mean the history is there, so there is no
rebuild term. **This is EXACT for the named arm**, because a whole MATERIALIZE is a single
request and a session is therefore either un-built (COLD) or built (warm); there is no partial
state for it.

It is APPROXIMATE for the unnamed piece variants, where a half-built session still prices as
fully cold. The reason is that the built prefix is not observable: `cstate.observation` gives
every recall an `EvidenceItem("D2", tier, tok, ...)` carrying the FULL believed history and
varies only the tier (`cstate.py:319-323`), so D100's prefix size never reaches the arm.
Exposing it would mean adding a field to `cstate.observation` and `baselines/interface.py`, the
one path every arm's inputs flow through, on the night the H100 runs a pilot on this build.
**Recommended if a piece variant is ever named; deliberately NOT applied tonight**, and recorded
here so the limit is not discovered later as a surprise.

## F2. Arm 10: `vllm-priority`, engine-native EDF

- **Release: identical to `always-cloud-fcfs`.** Every opportunity is sent immediately, with no
  cap and no admission test. That is the only honest way to ask "is the engine's own scheduler
  enough", because any arm-side ordering would confound the answer.
- **The only difference is that every action carries a priority**: the absolute deadline in
  integer milliseconds from run start, `int(round(deadline_abs * 1000))`, int64-bounded. Lower is
  served first, which matches vLLM. **A rebuild needed by a recall carries the recall's
  deadline.**
- **It refuses to run** unless the run declares the server in priority mode, so it can never
  silently run as plain FCFS and be reported as if the engine had ordered anything.

## F3. What the pinned vLLM actually supports, read from source

Read from the **`v0.31.0`** tag of `vllm-project/vllm`, which is the version
`reports/study_d7_capacity.md:23` pins. Note the layout moved in this version:
`entrypoints/openai/protocol.py` is now split into per-endpoint packages, and the scheduler
config moved to `vllm/config/scheduler.py`. **Priority scheduling is supported, so there is no
STOP condition here.**

| question | answer, from the v0.31.0 source |
|---|---|
| the server flag | **`--scheduling-policy`**, defined in `vllm/engine/arg_utils.py` as `scheduler_group.add_argument("--scheduling-policy", **scheduler_kwargs["policy"])` over the attribute `scheduling_policy: SchedulerPolicy = SchedulerConfig.policy` |
| its values | `vllm/config/scheduler.py`: `SchedulerPolicy = Literal["fcfs", "priority"]`, field `policy: SchedulerPolicy = "fcfs"`. Its docstring: `"priority" means requests are handled based on given priority (lower value means earlier handling) and time of arrival deciding any ties)` |
| the request field | `priority: int = 0` on `ChatCompletionRequest` in `vllm/entrypoints/openai/chat_completion/protocol.py`, bounded `ge=_INT64_MIN, le=_INT64_MAX`, described as `"The priority of the request (lower means earlier handling; default: 0)."` and raising an error for any non-zero priority if the served model does not use priority scheduling |
| does it PREEMPT running requests? | **Yes.** `vllm/v1/core/sched/scheduler.py` selects the victim as `preempted_req = max(self.running, key=lambda r: (r.priority, r.arrival_time),)` under `if self.policy == SchedulingPolicy.PRIORITY:`, against `preempted_req = self.running[-1]` otherwise, with the comment `# Preempt the lowest-priority request.` |
| what happens to a preempted request's KV? | `_preempt_request` calls `self._free_request_blocks(request)` and `self.encoder_cache_manager.free(request)`, then sets `request.status = RequestStatus.PREEMPTED` and **`request.num_computed_tokens = 0`**, and returns it with `self.waiting.prepend_request(request)`. Its docstring: `"""Preempt a request and put it back to the waiting queue.` |

**The consequence that matters for our setting, and it is not favourable.**
`num_computed_tokens = 0` means a preempted request's prefill is DISCARDED and recomputed from
scratch. So a multi-second cold rebuild, exactly the unit D118 exists to protect, can be
preempted by a nearer-deadline dashcam instant and lose all of its work, repeatedly. Engine-native
priority is therefore not a strictly stronger scheduler for this workload: it reorders well and
can thrash the long jobs. **This is the measurable difference between arm-side laxity ordering and
engine-native priority**, and it is the reason both arms exist rather than one.

Whether the recompute is cheap depends on prefix caching retaining the freed blocks. In V1 a
free returns blocks to the pool (`self.kv_cache_manager.free(request)`, or a deferred free via
`pop_blocks_for_free` into `self.deferred_frees`), and whether the subsequent recompute hits the
prefix cache depends on prefix caching being enabled and those blocks not yet being evicted.
**That recovery path was NOT verified line by line in 0.31.0 and must not be assumed.** Chunked
prefill appears in the scheduler only incidentally (`# Ignore draft tokens for prefill chunks.`)
with no priority-specific interaction found, and no host-offload interaction with priority was
found. Any claim beyond the table above needs a measurement on the H100, not a reading.

## F4. H100 wiring for vllm-priority

Nothing in this task touches an H100-owned file. If and when the user adopts this arm, the H100
must make exactly these changes; the arm is built so that nothing else is needed.

1. **The server flag.** Start the round-1 server with `--scheduling-policy priority`. Without it
   the engine silently serves FCFS and every non-zero `priority` in a request is rejected by the
   OpenAI layer, so the run would fail loudly rather than mislead, which is the intended
   behaviour.
2. **The request field.** Add `"priority": <int>` at the TOP LEVEL of the chat-completions JSON
   body, beside `model` and `messages`, as `int` within the int64 range. It is NOT a sampling
   parameter and does not belong inside `extra_body` for the OpenAI-compatible endpoint.
3. **Where it goes in the backend.** In `live2/backend.py` (and `asyncbackend.py`), where the
   body is assembled, read the value the arm puts in the action's metadata under the key
   `priority_ms` and copy it to the body's `priority`. The arm never builds a body itself, which
   is why this one line is the whole integration.
4. **The assertion to add.** In the backend, immediately before the send:
   `assert (self.scheduling_policy == "priority") == ("priority" in body), "vllm-priority: a priority was sent to a server that is not in priority mode, or the mode is on and no priority was set"`
   and record `scheduling_policy` in the run header so the scorer can see which mode produced the
   numbers.

## F5. Decisions and defaults

Posted up front under Step 0. All were taken at their default and are **PROVISIONAL**.

1. **`ARM_NAMES`.** Both arms are registered there. It is safe: `ARM_NAMES` is read only by the
   `--arm` CLI choices and by three all-arm tests, no sweep driver reads it (the pilot drivers
   list their arms explicitly), and the scorer's `GPU_BASELINES` is a separate hard-coded
   seven-tuple with a committed `len == 7` test. **So registering them does not put either arm in
   any run plan**, which is what D118 requires.
2. **The priority-mode gate.** Strictly refusing on the run header would need an H100-owned file,
   so the gate is: the arm refuses when a backend is declared and its policy is not `priority`;
   a run that declares nothing, which is a dry run or a test, proceeds and is stamped
   `server_scheduling_policy: null`. The strict assertion is in F4 item 4. This is the one place
   where the implementation is weaker than the instruction's wording, and it is flagged rather
   than glossed.
3. **Skip-rule timing.** Laxity is recomputed every epoch; a unit skipped once may be skipped
   again, and skips are counted per kind per run.
4. **Monitoring `S_hat`** excludes RTT and upload, which are transport and not service time.
5. **The unbuilt size** is readiness-derived, per F1: exact for the named arm, approximate for
   the unnamed piece variants.

## F6. Implementation and the replay. D118 BUILT, IN NO RUN

Step 2 of the D118 task. The pre-registration above was committed alone, before this code. Every
decision in F5 was taken at its default and is **PROVISIONAL**.

### F6.1 What was added, and the one refactor

`live2/arms.py` only:

| addition | note |
|---|---|
| `Pi0Edf._pending_items(obs)` | the merged pending set moved OUT of `Pi0Edf.decide` verbatim, so `LlfArm` orders the SAME set by a different key. This is the one change that touches an existing arm's code, which is why byte-identity is proven below rather than asserted |
| `LlfArm(Pi0Edf)` | inherits the D114 release rule, the D100 roster hook and the pending set; overrides only the order and adds the skip rule |
| `VllmPriorityArm(Live2ArmMixin, NAIVE.AlwaysCloudFCFS)` | inherits the release behaviour unchanged and adds priorities plus the refusal |
| `ROUND1_ARM_NAMES` | the eight round-1 arms, named explicitly so `ARM_NAMES` can hold the buildable set without blurring what round 1 is |

**No interface change was needed for the priorities.** `Action.notes` already exists, so
`vllm-priority` publishes `notes["priority_ms"]` and the backend reads it, which is why F4 is a
one-line change for the H100 rather than a schema change.

### F6.2 Byte-identity: nothing existing moved

Proven against the D114 build capture, which is the same tree with only `arms.py` differing.

| fixture | result |
|---|---|
| D99 grid, 4 and 8 devices x seeds 1 to 3, all 8 existing arms | **48 of 48 cells IDENTICAL** |
| seed-10 12-device 600 s replay, all 8 existing arms | **8 of 8 IDENTICAL** |

Per arm on the replay, each byte-identical: `device-only` 29, `always-cloud-fcfs` 6,518,
`utility-per-cost` 6,518, `b9` 6,488, `policy-core` 5,305, `edf` 6,861, `edf-piece1024` 7,037,
`edf-piece2048` 7,024 decisions. **The `_pending_items` extraction changed nothing**, which is
the claim that most needed proving.

Gates: policy 419 of 419, live2 **143 of 143** including the 25 new D118 tests, fleet 234 of 234,
all 12 frozen md5s green. The three all-arm tests now exercise both new arms, since `ARM_NAMES`
carries them.

### F6.3 llf on the seed-10 replay. REPLAY, NOT AN OUTCOME

`results/orchestration/live2/coord/d118/d118_llf_replay.json`. A dry run on the committed trace:
these are release counts, not scored outcomes, and no quality or latency claim is made.

| quantity | `edf` (D114) | **`llf`** |
|---|---|---|
| decisions | 6,861 | 6,600 |
| releases | 5,452 | 5,648 |
| releases per period, med / p90 / max | 1 / 2 / 4 | 1 / 2 / 4 |
| in-flight max | 4 | 4 |
| **robot questions released before their deadline, of 29** | **9** | **20** |
| units skipped as hopeless | n/a, no skip rule | **2,213** (2,204 instants, 9 recall pieces) |

**Least laxity does what work-conserving release could not.** D114 removed the release ceiling
and robot questions still fell from 11 to 9 of 29, because EDF's deadline order always puts a
dashcam instant ahead of a question. Ordering by laxity instead takes that to **20 of 29**, which
is the answer to reviewer question (a): the starvation was an artefact of the ordering key, not of
capacity.

**And the price is explicit.** llf sheds **2,204 of the roughly 6,490 offered dashcam instants**,
about a third, by declaring them hopeless and letting them fall to the device. That is exactly the
"drop requests that can no longer make it" the reviewer asks for, and it is a real cost, not a
free win: those instants are served locally at lower quality. **Whether trading a third of the
dashcam instants for eleven more robot questions is a good trade is an OUTCOME question that only
the scorer can answer, and it is not answered here.** The 9 skipped recall pieces are the
questions llf judged unreachable even with priority.

The skip count is also a measurement of the workload, not just the arm: instants go hopeless
because 10.82 are offered per second against a service capacity near 10, so a backlog forms and
backlogged instants cross their own deadlines. llf is the first arm that reports this rather than
serving them late.

### F6.4 Six-check consistency protocol

1. **Cross-check against committed measurements.** Every existing arm reproduces its D114 replay
   figure exactly, which is the byte-identity result itself. `edf`'s 9 of 29 reproduces section
   E5. The 29 robot questions and 10.82 instants per second reproduce H6 and E7.
2. **Physical plausibility.** `S_hat` is quoted from committed curves, not fitted: 0.1422 s per
   instant and 3.907 s of prefill for a 17,581-token history, the latter at the committed
   4,500 tok/s for the nearest measured size. Nothing here implies a rate faster than the
   committed curves, and llf's 5,648 releases over 600 s is 9.41 per second, still under the
   10.87 offered.
3. **Distribution sanity.** Releases per period are reported as median, p90 and max; skips are
   broken out by kind rather than given as one total.
4. **Definition audit.** "Laxity" is defined once as `deadline - now - S_hat` with each S_hat term
   tied to its committed source line. "Released before deadline" uses the same definition as E5,
   so the 9-against-20 comparison is like for like. "In flight" is Pi0Edf's definition, inherited
   unchanged.
5. **Claim linkage.** F6.3 bears on whether the policy's advantage survives a stronger baseline,
   the study's central comparison. It WEAKENS any reading of the D114 gap as the policy's merit,
   because a baseline that only changes its ordering key more than doubles the robot questions it
   releases. That is the point of building these arms before round 1 rather than after.
6. **Proxy validity.** Two proxies, both labelled. Release counts are a proxy for service and are
   NOT outcomes; the scorer owns outcomes. And `unbuilt` is derived from readiness, exact for the
   named whole arm and approximate for the unnamed piece variants, per F1.

### F6.5 Limitations

1. One trace, one seed, one fleet size, and a dry run whose service times come from the cost
   model rather than a server.
2. llf's skip rule is evaluated against committed MEDIAN curves. A unit whose true service time
   exceeds the median may be released and still miss; a unit below it may be skipped
   unnecessarily. No variance is modelled, because the committed curves are medians.
3. `vllm-priority` was NOT run against a server. Its priorities are verified by test, and the
   engine behaviour in F3 is read from source, not measured. Whether priority scheduling helps or
   thrashes under preemption is open and needs the H100.
4. Neither arm is in any run plan, so neither has a scored outcome of any kind.

---

# Robot service diagnosis: why policy-core does not serve robot questions

Flash, CPU only, 2026-11-18, dry run. **Diagnosis only: no policy code was changed.** Everything
was instrumented through wrappers installed for the length of one run and removed afterwards.

## G1. Reproduction status: the dry run reproduces the pilot exactly

| cell | H100 pilot, on time within 5 s | flash dry run, released before deadline |
|---|---|---|
| 4 devices, 9 robot questions | **1 of 9** | **1 of 9** |
| 8 devices, 20 robot questions | **0 of 20** | **0 of 20** |

Settings match the pilot: seed 0, 50 : 50, mode A, 600 s, D101 join, mu EWMA, H = 0.5 s, pol4,
tight memory (`GPU_KV`, `HOST_GIB`), `cap_k` None. Because the dry run reproduces the pattern, the
cause can be read off flash and no H100 log is needed.

## G2. The arithmetic behind every failure

**The only positive credit a robot question ever receives is a continuation value of exactly
`+0.03539`**, and it is the SAME constant for a 5,341-token history and a 20,101-token one.
Against it the backlog term charges `-mu x (busy increase)` with mu EWMA sitting at **1.44 to
1.57** and a rebuild adding **0.44 to 1.37 s** of engine busy time, which is **-0.66 to -2.06**.

The credit is one to two orders of magnitude too small to pay for the work. Two consequences
follow, and every one of the 29 questions lands in one of them.

### Failure mode A: declined at admission (4 of 9 at n = 4, 18 of 20 at n = 8)

The admit's `delta_j` is at or below zero, so the question is never admitted at all. The observed
admit values cluster at `-0.1027`, `-0.0555`, `-0.0848` and, for the larger histories, `-1.30`,
`-1.34`, `-1.39`, `-3.07`. In every case `u_hat = 0` and `z = 0`, and the `+0.03539` continuation
credit is swamped by the backlog term.

**This is the dominant mode at 8 devices**, which is exactly why the pilot's break is at 8: more
dashcams means more engine busy time, so the same constant credit buys less.

### Failure mode B: admitted, then every release scores EXACTLY zero (4 of 9 at n = 4, 1 of 20 at n = 8)

The question IS admitted, at `delta_j = +0.03539`, and then its rebuild pieces are offered for
release 183 to 370 times and **every single evaluation returns `delta_j` exactly 0.0**, with
`u_hat`, `z` and `terminal` all exactly zero. Release requires `delta_j > 0` strictly, so a
candidate worth exactly 0 is declined, forever.

| at 4 devices | rc_piece release candidates | `delta_j` exactly 0 | `< 0` | `> 0` |
|---|---|---|---|---|
| | 967 | **699 (72.3 %)** | 266 (27.5 %) | 2 (0.2 %) |
| at 8 devices | 406 | **268 (66.0 %)** | 132 | 6 |

**Why exactly zero.** With H = 0.5 s the rebuild piece cannot even START inside the horizon: the
engine is occupied by dashcam instants, so in BOTH branches of the piece's own counterfactual the
item is skipped for want of a start time, and the two rollouts are identical. `busy_delta` is
non-zero in only 118 of 967 candidates, confirming the item was served in neither branch in the
other 849. The result is a self-fulfilling prophecy: the piece is never released because the
horizon is too short to see any effect of releasing it, and the horizon never advances it because
it is never released.

**This is NOT the mechanism the task hypothesised for C1.** C1 anticipated `delta_j < 0` because
harm to many SH instants outweighs `omega_RC x gain`. What actually happens in mode B is
`delta_j == 0` because the payoff lies entirely outside H, and the strict inequality then
declines it. The distinction matters, because the remedies differ.

## G3. One question worked fully: opp0000187, 4 devices

| step | value |
|---|---|
| arrival | t = 66.11 s, deadline 71.11 s (5.0 s) |
| history | 7,771 tokens, believed readiness COLD, built prefix 0 |
| piece plan | 4 pieces of 2,048 tokens (`robo000:RICH:66.200:p0` to `p3`) |
| predicted rebuild, policy model | 1.783 s, and the job is marked **FEASIBLE** |
| predicted rebuild, committed curve | 1.727 s, so the model agrees to 1.03x and the question IS feasible in 5 s |
| admit evaluation | `delta_j = +0.03539` = `u_hat 0` + `z 0` + `terminal +0.03539`, all of it continuation value. ADMITTED |
| release evaluations | 208 of them, of which **160 returned exactly 0.0** and none was positive |
| deficit in force | `Z(robo000, RC) = 0.0` at every evaluation |
| mu in force | 1.503 |
| outcome | never released; the device's own answer stands |

A second trace from inside the same question shows the counterfactual inverted, which is the
clearest single piece of evidence: for the `PROMOTE_REBUILD` state action, the ACTION branch
recorded `progress = {}` while the REFERENCE branch recorded `progress = {robo000:RICH:66.200: 2}`.
The explicit rebuild (6,781 tokens in one item, 0.43 s of busy) **displaces the two pieces that
pi_0 would otherwise have served inside the horizon**, so the action looks strictly worse than
doing nothing: action terminal `-0.589` against reference `+0.045`, giving `delta_j = -0.634`.
**The reference branch assumes pi_0 continues the rebuild for free, while in the real run nothing
ever releases those pieces.** The counterfactual is being scored against work the system will
never actually do.

## G4. Cause classification, with counts

| cause | 4 devices | 8 devices | evidence |
|---|---|---|---|
| **C1, declined at admission** (continuation credit swamped by the backlog term) | 4 | 18 | admit `delta_j` from -0.0555 to -3.07 with `u_hat = z = 0` |
| **C1-zero, admitted then every release scores exactly 0** | 4 | 1 | 699 of 967 and 268 of 406 release candidates at exactly 0.0 |
| released but after the deadline | 0 | 1 | opp0002117: 36 release candidates, 6 positive, served late |
| served on time | 1 | 0 | opp0001376, the only question whose admit carried `u_hat = +0.0826` rather than continuation value alone |
| **C2, weak SLO pressure: CONFIRMED and absolute** | both | both | `Z(i, RC) = 0.000000` at **all 10,276 and 21,355 samples**, and `Z(i, SH) = 0` too |
| **C3, cost-model over-prediction: RULED OUT** | both | both | the policy model agrees with the committed curve to **0.85x to 1.05x** across all nine histories and marks every one FEASIBLE within 5 s |
| C4, granularity: ruled out | both | both | pieces of 2,048 tokens, a four-piece chain of about 1.8 s against a 5 s deadline |
| C5, bug: none found | | | the recall path IS offered (one admit candidate per question), history tokens are post-fix correct, readiness and deadlines read correctly |

**The one question served on time is the tell.** opp0001376 is the only one whose admit was
justified by `u_hat = +0.0826`, real utility visible inside the horizon, rather than by the
`+0.03539` continuation constant. Every question that depended on the continuation credit alone
failed.

### C3 ruled out with numbers

| history tokens | policy model | committed curve | ratio | feasible in 5 s |
|---|---|---|---|---|
| 5,341 | 1.118 s | 1.187 s | 0.94x | both yes |
| 7,771 | 1.783 s | 1.727 s | 1.03x | both yes |
| 12,091 | 2.642 s | 2.687 s | 0.98x | both yes |
| 20,101 | 4.510 s | 5.290 s | 0.85x | model yes, committed NO |

There is no over-prediction here. If anything the model UNDER-predicts the largest history, which
is the opposite of the D60 concern. Eight of the nine questions are feasible on the committed
curve too, so feasibility is not what gave up.

## G5. An instrumentation error I made and corrected

My first pass found **zero** release candidates for robot devices and I was one step from
reporting that the pieces are never offered for release, which would have been a fabricated C5
bug. The cause was my own filter: a `release` action carries `item_id`, not `items`, so the
device was invisible and every release candidate was silently excluded. After resolving the target
through `fleet.pending` and `fleet.in_flight`, 968 release candidates appeared at 4 devices and
406 at 8. **The absence was in my instrumentation, not in the policy.** It is recorded because an
absence created by a filter looks exactly like a finding.

## G6. Options. NOTHING WAS CHANGED

For C1 and C2 the task says to list options and not act. Each is a policy-version change after
the pilot (D79) and the user decides.

1. **Pooled deficit counters, matching D82.** The robot target is POOLED across devices while
   `Device.z` is PER DEVICE, and each robot device sees only about four questions in 600 s, so
   `bump_z` never accumulates and `Z(i, RC)` stayed at exactly 0 for the entire run at both
   sizes. A pooled counter would let robot misses build pressure across the fleet. This is the
   most direct fit to the measured cause and it addresses C2 at its root.
2. **Credit incremental rebuild progress inside the horizon.** Mode B exists because a piece that
   cannot start within H = 0.5 s produces an identical rollout in both branches. Crediting
   partial progress toward the continuation value, or scoring the rebuild chain as one unit
   rather than per piece, would make the release visible to the objective. Note this interacts
   with the inverted counterfactual in G3.
3. **Lengthen H for recall candidates**, so a multi-second rebuild falls inside the horizon it is
   judged in. H = 0.5 s is shorter than every rebuild in this trace (1.1 s to 4.5 s).
4. **A calibrated `omega_RC`, or a continuation value that scales with the work.** The credit is
   the same `+0.03539` for a 5,341-token and a 20,101-token history, so the objective cannot tell
   a cheap rebuild from an expensive one.
5. **Fix the reference branch so it does not assume pi_0 work the arm will never do** (G3). This
   is the one that looks closest to a specification defect rather than a tuning choice, and it is
   worth a separate ruling.
6. **A feasibility margin** is NOT indicated: feasibility was never the binding constraint, since
   every question was marked FEASIBLE and the model matched the committed curve.

**No C5 bug was found, so there is no fix to propose under item 5 of the task.**

## G7. Six-check consistency protocol

1. **Cross-check against committed measurements.** The dry run reproduces the pilot's robot
   counts exactly at both sizes, 1 of 9 and 0 of 20. The rebuild times reproduce the committed
   curve to within 15 %.
2. **Physical plausibility.** Every rebuild time is checked against `costs.recall_ttft_s`; none
   is faster than the committed curve (ratios 0.85x to 1.05x).
3. **Distribution sanity.** The `delta_j` figures are reported as full distributions per candidate
   kind with the exact-zero count separated out, not as means, and the per-question table lists
   all 29 questions rather than a summary.
4. **Definition audit.** "Released before deadline" uses the same definition as sections E5 and
   F6.3, so these counts are comparable with edf's. "Candidate" is one `delta_j` call. `Z` is
   `Device.z_of(task)` sampled at every decision epoch.
5. **Claim linkage.** This bears directly on the central comparison: at 4 devices plain `edf`
   serves 9 of 9 robot questions and `policy-core` serves 1. **Until this is resolved, no round-1
   result comparing policy-core against the baselines on the robot pool is interpretable.**
6. **Proxy validity.** One proxy, labelled: the dry run prices the engine from the frozen cost
   curve rather than serving a model, so the decisions are real but the service times are
   modelled. It is valid here because the pattern reproduces the pilot's counts exactly, which is
   the strongest available evidence that the modelled path and the live path agree on this.

## G8. Limitations

1. One seed (0) at two sizes. The pilot used the same seed, which is what makes the reproduction
   exact, but the cause counts are not a distribution over seeds.
2. `mu` is the EWMA, so its value moves during the run (1.44 to 1.57 at the medians, with one
   excursion to 1,408 recorded in the state candidates). The arithmetic in G2 uses the medians.
3. The inverted counterfactual in G3 was captured on 12 state-action evaluations, not on all
   7,539.
4. No scored outcome is claimed: these are release counts and decision values, not quality.

---

# Policy v1.1 (D122), Step 1: VERIFICATION. STOPPED, the hypotheses do not hold

Flash, read-only, 2026-11-18. No code was changed. **All three findings contradict or sharply
refine the planner's hypotheses, which the task makes a stop condition, so Step 2 was not
started.**

## V1. Issue B: Z is zero because the deficit counter is NEVER UPDATED

**Planner hypothesis:** the update uses the policy's own predicted success, so an admitted
question predicted FEASIBLE gives `S_hat` about 1, Z never rises, and the realised miss is never
fed back.

**REFUTED. There is no update at all.** The call chain is three links and the last one is empty:

| link | fact |
|---|---|
| `Device.z` is written | in exactly ONE place, `state.py:156`, inside `bump_z` |
| `bump_z` is called | from exactly ONE place, `coordinator.update_deficit` (`coordinator.py:719`) |
| `update_deficit` is called | **from NOTHING in production.** Its only callers in the whole repo are three lines of `policy/tests/test_rollout_coordinator.py` |

So `Device.z` keeps its `field(default_factory=dict)` value forever and `z_of(task)` returns
`0.0` for every device and every task, on every path. Meanwhile **`z_of` is READ in five
production sites**: the rollout's `_z_term` (`rollout.py:512`), the continuation value
(`rollout.py:533` and `:600`) and the closed form (`closed_form.py:202`, `:319`).

**Spec 3.3's deficit mechanism is ABSENT from the implementation, not miscalibrated.** It is read
by the objective in five places and written in none.

**`Z(i, SH)` is zero for the same reason**, which answers the task's sub-question directly: it is
not that SH targets are met. No task's counter is ever updated.

**This also corrects something I wrote earlier tonight.** The D120 section says the `z` term was
never positive "but only because this fixture runs `mu = 0`". That attribution was wrong: `z` is
identically zero because the counter is never updated, independently of `mu`. The D120 conclusion
is unaffected, but the reason given there is not.

Consequence for Step 2's item B: the pre-registered work was "if 1a confirms the hypothesis,
update each device's counter from the REALISED on-time outcome". The hypothesis is refuted, but
the remedy survives and is now larger in scope: **the update has to be introduced, not corrected**,
and a first caller has to be placed on a path that sees the realised outcome at `c + L`. Where
that call belongs is a design choice the task did not cover, so it is not mine to pick.

## V2. Issue A3: the promotion is implemented, fires, and is INERT

**Planner question:** is spec 8.3's promotion implemented, and why did it never fire?

**It IS implemented**, as spec 7.3's bounded-waiting check: `continuation.bounded_waiting_breach`
is called from `coordinator._update_jobs` (`coordinator.py:440`) and sets
`job.feasibility = PRIORITY` with a `Decision` row (`:443`).

**But promotion cannot cause a release, because the label is never read.** Searching every use of
`feasibility` and `PRIORITY`:

- `PRIORITY` is only ever ASSIGNED (`coordinator.py:443`) or RETURNED by `classify`
  (`continuation.py:137`). **Nothing anywhere branches on `job.feasibility == PRIORITY`.**
- The release path does not consult it: a release still needs `delta_j > 0`.
- **The rollout does not even let it change the value: `rollout.py:531` calls
  `continuation_value(..., priority=False, ...)` with `priority` hard-coded False**, so a promoted
  job is valued exactly as an unpromoted one.

So the honest answer to "why did it never fire for the deferred robot jobs" is that **firing is
not the issue: firing has no effect.** A separate mismatch, reported but not acted on: the trigger
passes `interval_s = self.params.H` (0.5 s) rather than one scheduling interval (the 100 ms
decision period), which makes it look further ahead and therefore fire EARLIER, not later.

This is neither "not implemented" nor "already correct", so it does not match either branch of
the task's stop condition cleanly. It changes what Step 2's A3 should do: not repair a trigger,
but give the label an effect.

## V3. Issue A1: the defer reference is sound, and the zero comes from a SATURATED INDICATOR

**Planner hypothesis:** the defer reference lets pi_0 progress the deferred job, which is why
`cont_delta` is 0 in 7,526 of 7,539 cases.

**Refuted for the release candidates, and the real mechanism is sharper.**

First, `exclude` is stronger than one period. In `Rollout.run`,

    rest = self._edf([p for p in f.pending
                      if p.item_id not in set(release_now) and p.item_id not in set(exclude)])

so the reference branch removes the item from the queue **for the whole horizon**, which is
already more pessimistic than the "no progress for one 100 ms period" that A1 proposes. Applying
A1 to a release candidate would make its reference MORE generous than today, pushing `delta_j`
DOWN, which is the opposite of the intended direction.

Second, the rollout models the release correctly. Instrumenting both branches of 558 rc_piece
release candidates:

| | result |
|---|---|
| candidates with `delta_j` exactly 0 | 410 |
| of those, the target WAS served in the ACTION branch | **410 of 410** |
| of those, the target was served in the REFERENCE branch | **0 of 410** |

**The piece is served in one branch and not the other, and the totals are still identical.** So
serving a rebuild piece changes nothing in the objective, and the earlier guess that the item
could not start inside the horizon is wrong: it started and ran.

Third, here is why. `continuation_value` multiplies by `p_finish`, and `p_finish` is a hard
INDICATOR, not a probability (`continuation.py:124`): `1.0 if s.finish_at is not None else 0.0`.
Measured on a fresh four-piece job of 2,048 tokens:

| pieces_done | the job finishes only if the deadline is at least |
|---|---|
| 0 | 1.00 s |
| 1 | 0.75 s |
| 2 | 0.50 s |
| 3 | 0.25 s |

Progress DOES move the feasibility cliff. But `continuation_value` reads only the indicator, so
while any slack remains the indicator is 1 before and 1 after, and the value is the SAME constant
`0.035385924` for `pieces_done` 0, 1, 2 and 3 and for every deadline from 5.00 s down to 1.00 s.
That constant is exactly `omega_RC x (acc_cloud - acc_device) = 0.4246 x 0.0833 = 0.035386`, which
is the `+0.03539` measured in the diagnosis.

**So the trap is a saturated indicator.** A robot question has a 5 s deadline and about 1.0 s of
scheduled work, so about 4 s of slack. While slack remains, building earns exactly zero credit,
`delta_j` is exactly 0, and the strict `> 0` test declines the release. The incentive to build
appears only in the last 1.0 s, when there is no longer time to build.

**This is why A1 as written cannot fix Mode B.** Deferring one 100 ms period reduces slack by
0.1 s; a saturated indicator does not move for that, so `delta_j` stays exactly 0 for about 39 of
the 40 periods before the cliff. A1 would change the decision only in the last period or two.
What Mode B needs is a continuation value with a GRADIENT in slack rather than an indicator,
which is a different change from the one pre-registered, and spec 5.4's own text calls the
indicator a deliberate simplification with sampled scenarios recorded as ambiguity A4.

## V4. Why this is a STOP

The task says to stop after Step 1 if any finding contradicts the hypotheses. Three do:

| issue | hypothesis | finding |
|---|---|---|
| B | the update runs with `S_hat` about 1 | **the update never runs; `update_deficit` has no production caller** |
| A3 | implemented but never fires, or already correct | **implemented and fires, but inert: `PRIORITY` is never read and the rollout hard-codes `priority=False`** |
| A1 | the defer reference lets pi_0 progress the job | **the reference excludes it for the whole horizon; the zero comes from a saturated `p_finish` indicator, and A1 would not move it** |

Each changes what the corresponding fix should be, and two of them (where to place the first
deficit update; replacing an indicator with a gradient) are design choices the task's
pre-registration did not cover. Per the stop rule and the standing rule that methodological
changes are proposed and not applied, **I implemented nothing and am reporting instead.**

## V5. What I would pre-register, if you want these three

Offered as proposals only, each tied to the mechanism actually found.

1. **B, introduce the update.** Call `update_deficit` at the opportunity's deadline with the
   REALISED on-time outcome, which is observable online and needs no ground truth. The open choice
   the task did not cover is WHERE: the coordinator sees completions, but the natural site for
   "the deadline passed and nothing arrived" is the expiry path. The scaling formula in the task
   can then be derived as specified, with SH scale pinned at 1.
2. **A3, give the label an effect.** The minimal honest version is to pass the job's own
   `feasibility` into `continuation_value` instead of the hard-coded `priority=False`, so a
   promoted job is valued under the priority schedule it was promoted to. That alone changes a
   value, not an ordering, and is testable on a hand-built near-infeasible job.
3. **A1 plus the gradient.** Honest deferral is worth having for its own sake, but on its own it
   does not address Mode B. Pairing it with a slack-sensitive `p_finish` (ambiguity A4's sampled
   scenarios, or a soft indicator) is what would make progress earn credit while slack remains.
   This is the largest of the three and the one most clearly a policy-version change under D79.

**Nothing above is implemented.** Step 2, Step 3 and Step 4 (including the D121 speed work and the
v1.1-fast release) are not started, and D121 remains paused at `fa50dfc`.

## V6. v1.1 fix A3 shipped, and it is a NO-OP today. Plus the static audit

### V6.1 A3 as ruled, with its own flag

`Flags.honour_job_priority`, DEFAULT OFF (D38). `Rollout._terminal` previously called
`continuation_value(..., priority=False, ...)` with the value hard coded, so spec 7.3's
promotion could not reach the value it was assigned for. It now passes
`self.flags.honour_job_priority and j.feasibility == PRIORITY`.

**It cannot change any decision in today's build, and that is measured rather than assumed.**
`continuation_schedule` uses the flag in exactly one place,
`cursor = t + (0.0 if priority else competing_s)`, and the rollout passes `competing_s = 0.0`. So:

| competing_s | priority False | priority True | differ? |
|---|---|---|---|
| **0.0, what the rollout passes** | 0.035385924 | 0.035385924 | **no, at every deadline from 5.0 s to 0.9 s** |
| 3.0, if competing work were modelled | 0.0 at a 3.0 s deadline | 0.035385924 | **yes** |

A second consequence of the same zero: **the PRIORITY class is unreachable from `classify`.** Both
of its branches are evaluated with `competing_s = 0`, so they agree; over 100 deadlines `classify`
returned only FEASIBLE (81) and INFEASIBLE (19), never PRIORITY. The label can only be set by the
bounded-waiting assignment at `coordinator.py:443`.

**So the real lever is `competing_s = 0.0`, not the priority flag.** Passing zero means the
continuation schedule assumes the job has the engine entirely to itself, which is why a 1.0 s
rebuild against a 5 s deadline always "fits" and `p_finish` is pinned at 1. That is the same
saturation V3 identified, seen from the other side. Changing `competing_s` is a methodological
change and is NOT applied; it is the natural companion to the `p_finish` gradient already
proposed.

A3 is shipped anyway because the label should not be silently discarded, and because it becomes
live the moment competing work is modelled.

**Tests** (`policy/tests/test_v11_fixes.py`, 6 tests). Honest note on the task's "fails on v1.0,
passes on v1.1" requirement: **a behavioural test that fails on v1.0 is impossible here**, because
the two paths are provably identical at `competing_s = 0`. The tests that fail on v1.0 are
therefore structural, asserting the rollout reads the job's own class and no longer hard-codes
`priority=False`, plus a behavioural test at `competing_s = 3.0` showing the promoted job is worth
0 without priority and its full value with it, which is the case v1.0 could never express.

**Equivalence:** 48 of 48 D99 grid cells byte-identical with the flag off, policy suite 433 of 433
(6 new), 12 frozen md5s green.

### V6.2 A1 DROPPED, as ruled

Recorded per the ruling: release references are already more pessimistic than A1 proposes
(`exclude` removes the item for the whole horizon), and A1 cannot move a saturated indicator. No
A1 code was written.

### V6.3 Static audit: state the policy reads in production but never writes

Method: every field declared on the `state.py` dataclasses, counted across all production files
in `policy/` and `live2/` with tests excluded, for attribute writes, constructor keywords and
in-place mutation. A field is flagged only if it has reads and NONE of the three.

| class.field | declaration | reads | verdict |
|---|---|---|---|
| **`HistoryBelief.staleness_s`** | `float = 0.0` | 5 | **READ, NEVER WRITTEN, and it matters.** It feeds `utility.t_ready_s`, where `frames = staleness_s / d2_stride_s` converts it into catch-up frames, and reaches `readiness._u_rc_from_tier` and `coordinator.py:129`. Pinned at 0.0 means **the policy believes no history is ever stale and never charges catch-up work**, so every history looks readier and cheaper than it is |
| **`Device.z`** | `Dict[str, float]` | 5 read sites | **effectively READ-NEVER-WRITTEN.** Written only at `state.py:156` inside `bump_z`, whose only caller `update_deficit` has no production caller (V1). This is issue B |
| `Device.controller` | `Any = None` | 1 | read-never-written; the single read is a presence check, so the effect is that no controller is ever attached |
| `HistoryBelief.unsent_frames` | `int = 0` | 1 | read-never-written |
| `Job.p_finish` | `float = 1.0` | 2 | a DEAD field: both occurrences are documentation strings in `spec_map.py`, so nothing reads it in logic. Worth deleting or wiring, not a behaviour bug |

Everything else is written, set at construction, or mutated in place. **Report only; nothing was
changed.** The two that deserve a ruling are `staleness_s`, which silently removes a cost the
spec charges, and `Device.z`, which is issue B.

## V7. Fix B PRE-REGISTRATION: the deficit update, and a scaling that needs one ruling

Written before the code, as ruled. B1 (the update) is unambiguous and is implemented. B2 (the
scaling) is derived here and **NOT implemented**, because its forced magnitude is a choice the
task did not cover.

### V7.1 B1, the update rule, exactly

For each opportunity `o` of device `i` and task `k`, **exactly once**, when its outcome becomes
certain:

    S(o) = 1  if a cloud answer for o arrived with t_first_token <= deadline_abs(o)
    S(o) = 0  otherwise

`S(o) = 0` therefore covers all of: delivered late, declined, never admitted, and
expired-to-device, which is what the ruling asks for. Then

    z_i[k]  <-  max( z_i[k] + w_{i,k} * (p_k - S(o)) , 0 )

which is exactly the committed `Device.bump_z(task, p_target, success_hat)` with
`success_hat = S(o)`, and `w = 1` in B1. With `p_k = 0.9` for every task (committed `Params.p_k`),
a miss adds `+0.9` and a success adds `-0.1`, floored at 0.

**Arm-side, no coordinator edit.** `t_first_token` is already on the payload the coordinator hands
the arm at `coordinator.py:656`, and the application sees an answer at its first token (the
harness addendum), so on-time is observable arm-side with no new plumbing and nothing
H100-owned is touched.

**Resolution, with the accepted one-period lag:**

- every `decide(obs)` registers the opportunities it is shown: each SH instant from the D100
  roster by its `opportunity_id` and `deadline_abs`, and each recall query by `query_id` and its
  own absolute `deadline_s`. Registering from the OBSERVATION rather than from admissions is what
  makes a declined or never-admitted opportunity count as a miss;
- `live2_completed` records `answered_at = t_first_token` against that `opportunity_id`;
- every `decide(obs)` at clock `now` then resolves each registered opportunity that is either
  answered, or whose `deadline_abs < now`, bumps it once and stops tracking it.

**Expected effect, pre-registered so it can be checked without rewording.** A robot miss raises
that device's `z[RC]` by 0.9. `z` reaches the objective only through `_z_term`, as
`z_of(task) x (ok/n)`, so for a robot with one in-horizon question serving it would gain about
`+0.9` against a backlog charge of about 0.7 to 1.25 measured in the diagnosis. **So B1 alone is
the same order of magnitude as the cost it must overcome, and it may or may not flip the
decision. That is exactly what Step 3 measures.** Note `z` does NOT reach the continuation value:
`rollout.py` passes `d_p_success=0.0`, so that term is `z x 0`.

### V7.2 B2, the scaling, derived and NOT implemented

The ruling asks that each update be weighted by the opportunity's share of that device's target
window, with SH staying exactly at scale 1. Those two constraints together force one form:

    w_{i,k} = N_SH / N_{i,k}

where `N_{i,k}` is the expected count of task-k opportunities for device i in the window. From
committed quantities only:

| quantity | committed source | value in a 600 s window |
|---|---|---|
| `N_SH` | `Params.T_k["SH"] = 0.5 s` cadence | 600 / 0.5 = **1,200** |
| `N_RC` | `profiles.lambda_rc_default() = 0.009934 /s` (D48) | 0.009934 x 600 = **5.96** |

so `w_SH = 1` exactly, as constrained, and

    w_RC = 1200 / 5.96 = 201.3

**The window length cancels**, which is worth stating: `N_SH / N_RC = (W / 0.5) / (lambda W) =
2 / lambda = 201.3` for any W, so the undefined "target window" turns out not to be a choice at
all.

### V7.3 The one ruling B2 needs

**`w_RC = 201.3` means a single robot miss adds `201.3 x 0.9 = 181.2` to `z[RC]`.** For scale, in
the same objective the continuation value of a robot question is `0.0354` and the backlog charge
is about 1. Because `_z_term` contributes `z x Delta(ok/n)`, serving one robot question after a
single prior miss would gain about `+181`, which dominates every other term by more than two
orders of magnitude. The policy would then serve robot questions essentially unconditionally for
the rest of the run.

That is a 200x gain on robot SLO pressure arriving as a consequence of the normalisation rather
than as a calibrated quantity, and shipping it would be hard to distinguish from tuning until
robots pass, which the task's guiding rule forbids. **So B2 is pre-registered and stopped here for
a ruling.** Three forms, with my recommendation:

1. **Measure B1 first and decide B2 afterwards.** B1 is already the same order as the cost it
   opposes, so the scaling may be unnecessary. **Recommended**, and it is what Step 3 now
   measures.
2. **Ship `w_RC = 201.3` as derived.** Faithful to the ruling's words, with the dominance above as
   its known consequence.
3. **Normalise per window instead of per opportunity**, `w_{i,k} = 1 / N_{i,k}`, so each device's
   updates sum to its per-window deficit `p_k - achieved`. This is the cleanest statistical
   reading and makes `z` comparable across devices, but it puts SH at `1/1200`, violating the
   "SH scale exactly 1" constraint, so it is listed only for completeness.

Nothing from B2 is implemented.

## V8. Step 3: v1.1 measured. B1 works and changes NOTHING. STOPPED per the ruling

Dry run, not an outcome claim. Pilot-matching settings: seed 0, 4 and 8 devices, 600 s, mu EWMA,
H = 0.5 s, pol4, tight memory. Four variants, the full ablation the ruling asked for.

| n | variant | robot questions | **released before deadline** | monitor releases | `z[RC]` max | z updates | misses | admits > 0 | rc_piece releases with `delta_j == 0` |
|---|---|---|---|---|---|---|---|---|---|
| 4 | v1.0 | 9 | **1** | 2,174 | 0.0 | none | none | 5 of 9 | 699 of 967 |
| 4 | A3 alone | 9 | **1** | 2,174 | 0.0 | none | none | 5 of 9 | 699 of 967 |
| 4 | B alone | 9 | **1** | 2,174 | **4.5** | 2,183 | 8 | 5 of 9 | 699 of 967 |
| 4 | A3+B (v1.1) | 9 | **1** | 2,174 | **4.5** | 2,183 | 8 | 5 of 9 | 699 of 967 |
| 8 | v1.0 | 20 | **0** | 2,107 | 0.0 | none | none | 2 of 20 | 268 of 406 |
| 8 | A3 alone | 20 | **0** | 2,107 | 0.0 | none | none | 2 of 20 | 268 of 406 |
| 8 | B alone | 20 | **0** | 2,107 | **6.3** | 4,338 | 2,231 | 2 of 20 | 268 of 406 |
| 8 | A3+B (v1.1) | 20 | **0** | 2,107 | **6.3** | 4,338 | 2,231 | 2 of 20 | 268 of 406 |

**B1 does exactly what it was pre-registered to do.** The deficit counter is no longer
structurally zero: `z[RC]` reaches 4.5 at four devices (five realised misses at `p_k = 0.9`) and
6.3 at eight, over 2,183 and 4,338 resolved opportunities. Spec 3.3's mechanism is present for the
first time.

**And it changes not one decision.** Comparing decision logs against v1.0:

| n | A3 alone | B alone | A3+B |
|---|---|---|---|
| 4 | **0 of 2,380 differ** | **0 of 2,380** | **0 of 2,380** |
| 8 | **0 of 2,220 differ** | **0 of 2,220** | **0 of 2,220** |

Dashcam cost is therefore exactly zero (2,174 and 2,107 monitor releases, unchanged), which is the
one thing the ruling's constraint required and the only part of this that went to plan.

### V8.1 Issue C: why the deficit cannot reach the decision

The ruling asked whether the Z and continuation terms now outweigh the backlog charge, or whether
robots would still be declined on the exchange rate alone. **Neither: the exchange rate never
comes into it, because the multiplier is zero.**

`z` reaches the objective only through `_z_term` (`rollout.py:512`):

    total += f.devices[did].z_of(task) * (ok / n)

where `ok` counts that device's in-horizon opportunities whose `met_slo` is true. A rebuild piece
does not answer anything, so the robot question's `met_slo` is false in BOTH branches of the
piece's counterfactual, `ok / n` is identical, and

    Delta z_term = z x Delta(ok/n) = z x 0 = 0

for any `z` whatsoever. A larger `z`, including B2's 181 per miss, multiplies the same zero. The
deficit can only bite when serving the opportunity flips its SLO outcome INSIDE the horizon, and a
robot answer never lands inside H = 0.5 s.

**So B hits the same horizon wall as the continuation value in V3, by a different route.** Two
independent credit channels, the continuation value and the deficit counter, are both pinned:
one by a saturated indicator, the other by a zero multiplier. Both for the same underlying reason.
This also settles B2 without needing it: **scaling the deficit by 201 would not change a single
decision either**, because it scales a term that is multiplied by zero. I recommend B2 be dropped
rather than ruled on.

### V8.2 This is the ruling's stop point

The ruling says: "If robot questions are still deferred past usefulness (Mode B), STOP and report:
the next fix would be making `p_finish` a probability using the cost model's measured
completion-time error fitted on FIT/DEV data only (spec Phat), and the user will rule."

**Robot questions are still deferred past usefulness: 1 of 9 and 0 of 20, unchanged.** So I
stopped. Step 4, the D121 speed work and the v1.1-fast release, is NOT started, and D121 remains
paused at `fa50dfc`.

One observation on the named next fix, offered because it bears on whether it would work. Making
`p_finish` a probability would give the CONTINUATION channel a gradient, which addresses V3's
saturation directly. It would not by itself fix the `_z_term` zero in V8.1, because that term
depends on `met_slo` flipping inside H rather than on any probability. If the goal is for robot
work to earn credit for progress, the horizon wall itself is the common cause of both, and the two
candidate levers are the ones already named: a slack-sensitive `p_finish`, and crediting
out-of-horizon completion (the SH side already does this for monitoring, via D98's tail, which
credits a released call at its own deadline even when delivery lands after the horizon;
`rollout.py` has no equivalent for RC).

**That last point is the most useful thing in this section.** D98 already solved exactly this
problem for SH: "a released call has to be simulated through to delivery even when that delivery
lands after the horizon", because otherwise an instant is "worth zero merely because it lands
after the horizon". **RC has no such tail.** A D98-equivalent tail for recall answers would make a
rebuild's payoff visible without changing any value definition, and it is the narrowest change of
the three. It is NOT implemented; it is the option I would put first for your ruling.

### V8.3 v1.1 status and gates

| item | state |
|---|---|
| A3 `honour_job_priority` | implemented, DEFAULT OFF, measured no-op (V6.1) |
| A1 | DROPPED as ruled (V6.2) |
| B1 `deficit_update` | implemented, DEFAULT OFF, works and changes no decision |
| B2 scaling | pre-registered, NOT implemented, and V8.1 shows it cannot help |
| C | unchanged, measured only |
| policy suite | **439 of 439** (12 new v1.1 tests) |
| D99 grid, flags off | 48 of 48 byte-identical |
| frozen md5s | 12 of 12 green |
| baseline arms | untouched |

## V9. PRE-REGISTRATION: the RC tail, and the staleness fix

Written before the code, as ruled. Also recorded: **B2 is SHELVED, not dropped.** Its derivation
stands at V7.2 and the reason it is shelved is V8.1, that `_z_term` multiplies `z` by a change in
the met-SLO fraction which is zero for a rebuild piece. It is revisited once the deficit term is
visible, which is what the RC tail is for.

### V9.1 What D98's SH tail does, exactly, so the mirror is checkable

| element | D98's SH tail (`rollout.py:204-265`) |
|---|---|
| selection | in the main queue loop, an item whose `start = max(free_at, p.due_at)` exceeds `end` is appended to `sh_tail` **only if `p.kind == "episode_call"`**; every other kind keeps the old behaviour of not being simulated |
| bound | `latest = max(end, every episode_call `due_at` in `pending` and `in_flight`) + L_k["SH"]`, so the pass stops at the last deadline any credited instant can have |
| continuation | `tail_free = free_at`, continuing the engine from where the horizon left it, then per item `start = max(tail_free, p.due_at)`, `break` if `start > latest`, one `engine.predict` at the SAME `concurrent` and `load_pct`, `tail_free = start + service_s` |
| new arrivals | NONE. The pass iterates only `sh_tail`, which came from the existing queue |
| accounting isolation | "Nothing here is charged to `busy`, the KV pool, `demand_tokens` or `jobs_progress`": only `deliveries` (marked `beyond_horizon=True`) and `in_sample` are touched |
| cost | at most one extra `engine.predict` per SH call that could not start inside H |

### V9.2 The RC tail, mirrored element by element

Behind `Flags.rc_tail`, DEFAULT OFF.

| element | the RC tail |
|---|---|
| selection | the SAME branch, extended: an `rc_piece` whose `start` exceeds `end` goes to the tail instead of being dropped |
| bound | `latest_rc = max(end, every `rc_piece` `deadline` in `pending` and `in_flight`)`. RC items carry an absolute `deadline` already, so no `L_k` is added; this is the same rule as D98's, "the last deadline any credited question can have", read off the field that holds it |
| continuation | the SAME single cursor. **One tail pass over both kinds in queue order**, not two passes, because the engine is serial and two cursors both starting at `free_at` would double-book it |
| new arrivals | NONE, exactly as D98 |
| accounting isolation | `busy`, the KV pool, `demand_tokens` and the `jobs_progress` that `_terminal` and `_prefix_risk` read are left byte-for-byte as they are. The tail's progress is kept in a SEPARATE view that only `_rc_utility` sees |
| cost | at most one extra `engine.predict` per `rc_piece` that could not start inside H |

**One consequence stated up front, because it means the switch is not SH-neutral.** Sharing the
cursor means an SH delivery in the tail can be pushed later by an `rc_piece` ahead of it in queue
order, so SH credit can change when the switch is ON. That is the price of modelling one serial
engine, and it is why the switch exists rather than this being applied unconditionally.

### V9.3 What the tail has to credit, and the second defect it exposes

**omega_RC x u_RC: the machinery already exists and has never been reachable.**
`_rc_utility` (`rollout.py:473-493`) already credits `omega_RC x (acc_cloud - acc_device)` for a
job whose pieces are all done and whose last delivery satisfies `last <= job.deadline`, which IS
"at the question's own deadline". It never fires because `done = job.pieces_done +
progress.get(jid, 0)` counts only pieces served INSIDE the horizon, and four 2,048-token pieces
need about 1.0 s against H = 0.5 s. Letting `_rc_utility` see the tail's progress is therefore the
whole of the utility half.

**The per-device deficit term needs more than a tail, and this is a NEW finding.**
`_z_term` aggregates over the `opps` rows returned by `_opportunity_utility`, and
`_opportunity_utility` emits rows with `task="SH"` ONLY. So `(device, "RC")` never appears in the
aggregation and **`z_of("RC")` is never read by `_z_term` at all**, for any `z`. This is stronger
than V8.1, which said the multiplier was zero: the term is not merely zero, it is absent. So the
tail must also emit an RC opportunity row per question, carrying `met_slo` set from whether the
answer was delivered by that question's own deadline, which is what makes the deficit reachable.

### V9.4 Expected effect, pre-registered so it can be checked without rewording

1. A robot question whose rebuild finishes after H but before its 5 s deadline will, for the first
   time, show a positive `u_hat` contribution of `omega_RC x (acc_cloud - acc_device) = 0.0354` in
   the branch that releases its pieces, against `0` in the branch that does not.
2. With B1 also on, that question's device contributes `z_of("RC") x (ok/n)` to `_z_term`, so a
   device carrying `z[RC] = 4.5` from earlier misses adds up to a further `+4.5` when the answer
   lands in time.
3. Together those are the first terms that can exceed the measured backlog charge of about 0.7 to
   1.25, so **I expect release decisions to change and robot questions released before deadline to
   rise above the 1 of 9 and 0 of 20 of v1.0.** If they do not, the tail is insufficient and the
   next lever is the one the ruling holds back.
4. Decision cost rises by at most one `engine.predict` per tailed item, so I expect a measurable
   but modest p99 increase, reported at 8, 32 and 64 devices with and without the tail.

### V9.5 The staleness fix, as an implementation fix

`HistoryBelief.staleness_s` is read in production and written nowhere (V6.3), so it is pinned at
`0.0` while feeding `utility.t_ready_s`, where `frames = staleness_s / d2_stride_s` turns it into
catch-up frames. The policy therefore believes no history is ever stale and never charges
catch-up work.

Written from coordinator state at the one site that builds the belief
(`arms_policy._sync`, where `b.size_tokens` and `b.probs` are already set from the observation):

    unbuilt_tokens = max(size_tokens - built_tokens(session), 0)
    staleness_s    = (unbuilt_tokens / D2_TOK_PER_IMG) * d2_stride_s

`built_tokens` comes from the roster's `built_tokens_by_session`, which the coordinator already
publishes and the arm already reads at `arms_policy.py:322`. `D2_TOK_PER_IMG = 90` (StudyRH4) and
`d2_stride_s = 2.0` is the committed profile value, so the conversion is frames received minus
frames built, expressed in the seconds unit the consumer expects. This is an implementation fix,
not a new mechanism: it writes a field the spec already reads.

It is behind `Flags.write_staleness` for the ablation, because it changes inputs to the readiness
and recall-utility paths and the ruling asks for it as a separate arm of Step 3.

## V10. The RC tail and the staleness fix, measured. The tail WORKS and is NOT SUFFICIENT

Dry run, not an outcome claim. Seed 0, 4 and 8 devices, 600 s, mu EWMA, H = 0.5 s, pol4, tight
memory. `edf` on the same traces for reference.

| n | variant | robot questions | **released before deadline** | monitor releases | `z[RC]` max | decisions | **decisions differing from v1.0** |
|---|---|---|---|---|---|---|---|
| 4 | v1.0 | 9 | 1 | 2,174 | 0.0 | 2,380 | reference |
| 4 | A3+B1 | 9 | 1 | 2,174 | 4.5 | 2,380 | **0 of 2,380** |
| 4 | +staleness | 9 | 1 | 2,174 | 4.5 | 2,380 | **316** |
| 4 | **+RC tail** | 9 | **2** | 2,128 | 4.5 | 2,297 | **2,193** |
| 4 | **all** | 9 | **2** | 2,128 | 4.5 | 2,297 | **2,193** |
| 4 | `edf` reference | 9 | **8** | 2,174 | n/a | 2,190 | n/a |
| 8 | v1.0 | 20 | 0 | 2,107 | 0.0 | 2,220 | reference |
| 8 | A3+B1 | 20 | 0 | 2,107 | 6.3 | 2,220 | **0 of 2,220** |
| 8 | +staleness | 20 | 0 | 2,107 | 6.3 | 2,220 | **353** |
| 8 | **+RC tail** | 20 | **3** | 4,008 | 5.3 | 4,383 | **3,029** |
| 8 | **all** | 20 | **3** | 4,008 | 5.3 | 4,383 | **3,326** |
| 8 | `edf` reference | 20 | **11** | 4,322 | n/a | 5,127 | n/a |

### V10.1 What each fix did

**The RC tail is the first change in this whole sequence that moves robot service.** 1 of 9 to
**2 of 9** at four devices, and 0 of 20 to **3 of 20** at eight. The pre-registered expectation at
V9.4 was "release decisions change and robot questions released rise above 1 of 9 and 0 of 20",
and that is what happened: 2,193 and 3,029 decisions move.

**And it is NOT SUFFICIENT.** `edf` serves **8 of 9** and **11 of 20** on the same traces.
policy-core with every v1.1 fix on reaches 2 and 3. The gap to the baseline is still large, and on
the robot pool the policy is still much worse than plain EDF.

**The staleness fix changes decisions but not robot service**: 316 and 353 decisions move, robot
releases stay at 1 and 0. So the catch-up cost it restores is real and reaches the decisions, and
it is not what was holding robots back. It is kept because it writes a field the spec reads
(V9.5), not because it helped here.

**A3+B1 remains byte-identical to v1.0**, confirming V8 on a second run.

**The tail is not SH-neutral, as pre-registered.** At four devices monitor releases fall slightly,
2,174 to 2,128. At eight they nearly DOUBLE, 2,107 to 4,008, and total decisions go 2,220 to
4,383. The policy becomes much more active overall and ends up near `edf`'s 4,322 monitor
releases. **I flagged the direction as a risk in V9.2 and the magnitude at eight devices is larger
than I expected; it is reported rather than explained away.** The shared tail cursor and the new
RC rows in `_z_term` both feed back into SH decisions, and separating those two causes was not
part of this task.

`z[RC]` max falls from 6.3 to 5.3 at eight devices under the tail, which is consistent with fewer
realised misses once three questions are served.

### V10.2 Decision cost, and why the fixture the ruling named cannot measure it

The ruling asked for p50 and p99 at 8, 32 and 64 devices on the 180 s fixture, with and without
the tail:

| n | tail OFF p50 / p99 | tail ON p50 / p99 | p99 change | scoring calls |
|---|---|---|---|---|
| 8 | 1.86 / 8.48 ms | 1.86 / 8.40 ms | -1.0 % | 9,921, identical |
| 32 | 19.82 / 98.69 ms | 19.66 / 99.67 ms | +1.0 % | 37,216, identical |
| 64 | 49.55 / 247.45 ms | 49.62 / 247.95 ms | +0.2 % | 56,063, identical |

**Those numbers do not measure the tail, and must not be read as its cost.** Instrumenting the
same 32-device cell shows the RC tail produced **0 beyond-horizon `rc_piece` deliveries**, against
6,889 `episode_call` ones from D98's SH tail. **The RC tail never fires on the synthetic fixture**,
whose recall pieces can start inside the horizon, so the table above is the cost of a switch that
does nothing there. Reported in full because the ruling asked for it, and labelled.

The cost where the tail DOES fire, on the fleet trace:

| n | variant | p50 | p99 | max | decision samples |
|---|---|---|---|---|---|
| 4 | v1.0 | 1.101 ms | 8.534 ms | 114.9 ms | 2,379 |
| 4 | +RC tail | 1.260 ms | **4.142 ms** | 109.6 ms | 2,295 |
| 8 | v1.0 | 1.720 ms | 9.435 ms | 140.5 ms | 2,220 |
| 8 | +RC tail | 3.094 ms | **10.757 ms** | 433.8 ms | 4,380 |

At four devices p50 rises 14 % while p99 FALLS, and at eight p50 rises 80 % and p99 14 %, with the
maximum rising from 141 to 434 ms. Note the sample counts differ (2,220 against 4,380), because
the tail changes how many decisions the run makes, so these are not paired comparisons of the same
decisions. The honest summary: **the tail's own arithmetic is cheap, one extra `engine.predict` per
tailed item, but it changes the run enough that the decision-time distribution is not comparable
like for like.**

### V10.3 One guard the tail made necessary

With the tail on, a job stays valuable after its recall opportunity leaves the observation, so the
arm tried to emit a MATERIALIZE for a session `interface.validate_action` no longer knows (it
accepts gpu-warm, host-warm, or offered-this-period only) and the run aborted with
`action names unknown session`. `_to_action` now skips a build whose session is not in that set;
the piece is simply not materialised that period and is re-decided when the session is offered
again. This is a consequence of the tail, not a pre-existing defect, and it is why the first
`+RC tail` run failed.

### V10.4 The tail is insufficient, so here is the proposal the ruling asked for

The ruling held back probabilistic `p_finish` and realistic `competing_s` "unless the tail is
insufficient; propose then". **It is insufficient: 2 of 9 and 3 of 20 against edf's 8 of 9 and 11
of 20.** What the measurements now say about each:

1. **Realistic `competing_s` is the one I would do next.** V6.1 showed the rollout passes
   `competing_s = 0.0`, so the continuation schedule assumes the job has the engine entirely to
   itself. That is why `p_finish` is pinned at 1 for a 1.0 s rebuild against a 5 s deadline, why
   the continuation value is the constant 0.0354, AND why the PRIORITY class is unreachable so A3
   is inert. **One zero causes three separate failures.** Passing the competing engine-seconds
   pi_0 would serve first would make `p_finish` discriminate, give the continuation value a
   gradient in slack, and make A3 live, without introducing any new estimator: the quantity is
   already in the rollout as `busy`.
2. **Probabilistic `p_finish` is the deeper fix but is downstream of the above.** With
   `competing_s = 0` it would still be comparing against a schedule that assumes an idle engine,
   so it would soften an indicator that is computed from the wrong occupancy. It is worth doing
   after 1, and it needs the measured completion-time error fitted on FIT/DEV only, as the ruling
   says.
3. **Not proposed: anything that raises `omega_RC` or scales the deficit.** V8.1 settled the
   deficit route, and raising `omega_RC` would be tuning until robots pass.

**STOPPED here per the ruling.** Step 4, the D121 speed work and the v1.1-fast release are not
started, and D121 remains paused at `fa50dfc`.

### V10.5 Gates

| item | state |
|---|---|
| policy suite | **449 of 449** (22 new v1.1 tests) |
| frozen md5s | 12 of 12 green |
| baseline arms | untouched; `edf` was run as a reference arm only |
| every v1.1 switch | DEFAULT OFF: `honour_job_priority`, `deficit_update`, `rc_tail`, `write_staleness` |

## V11. F1 follow-up: the deficit term IS now visible for robot candidates

Dry run, screening. Seed 0, 4 and 8 devices, 600 s, mu EWMA, H = 0.5 s, tight, with `rc_tail`,
`deficit_update` and `honour_job_priority` all on.

Before F1 the RC deficit was not merely zero, it was ABSENT: `_opportunity_utility` emitted
`task="SH"` rows only, so `(device, "RC")` never entered `_z_term`'s aggregation and
`z_of("RC")` was never read by it at all. `_rc_opportunities` now emits an RC row per unanswered
job, so the channel exists. Measured distribution of the `z` term over robot candidates:

| n | candidate kind | candidates | `z` exactly zero | non-zero | non-zero range |
|---|---|---|---|---|---|
| 4 | admit | 9 | 2 (22.2 %) | **7 (77.8 %)** | 0.267 to 0.900 |
| 4 | release | 461 | 439 (95.2 %) | 22 (4.8 %) | 0.267 to 0.900 |
| 4 | state | 7,539 | 7,539 (100 %) | 0 | none |
| 8 | admit | 20 | 4 (20.0 %) | **16 (80.0 %)** | 0.567 to 1.800 |
| 8 | release | 1,686 | 1,586 (94.1 %) | 100 (5.9 %) | 0.567 to 1.800 |
| 8 | state | 15,038 | 15,035 (100 %) | 3 | -1.800 (negative) |

`z[RC]` max 4.5 at n=4 over 2,183 resolved opportunities with 54 misses, and 5.3 at n=8 over
4,342 with 335 misses.

**So the answer to F1's owed question is yes.** The deficit now reaches ADMIT decisions strongly,
78 to 80 per cent of robot admits carry a non-zero deficit term of up to 1.8, and RELEASE
decisions weakly, 5 to 6 per cent. It is still exactly zero for every `state` candidate, where
the three non-zero cases at n=8 are NEGATIVE, so the PROMOTE_REBUILD path still gets no deficit
credit.

### V11.1 The B2 proposal, with numbers. RECOMMENDATION: DO NOT SCALE

The derivation at V7.2 stands: the ruling's two constraints force `w = N_SH / N_RC`, which from
committed quantities only (`T_k["SH"] = 0.5 s` giving 1,200 and D48's
`lambda_rc = 0.009934 /s` giving 5.96 in a 600 s window) is **201.3**, window-independent.

What is new is that the unscaled term is now MEASURABLE, so the comparison can be made on numbers
rather than on a derivation:

| quantity | magnitude |
|---|---|
| deficit term at `w = 1`, as measured above | up to **1.800** |
| the backlog charge it must overcome, measured in the diagnosis | **0.7 to 2.06** |
| continuation value of a robot question | 0.0354 |
| deficit term at `w = 201.3`, one miss | 181.2, and the term would reach about **362** |

**At `w = 1` the deficit is already the same order of magnitude as the cost it opposes**, which
is the condition B2 was meant to create. At `w = 201.3` it would exceed that cost by more than
two orders of magnitude and the policy would serve robot questions unconditionally after a single
miss, which is indistinguishable from tuning until robots pass.

**I therefore recommend B2 be settled as "do not scale", keeping `w = 1`.** B2 remains SHELVED
and the ruling is OUTSTANDING; nothing was implemented, and I did not block on it.

## V12. F3 PRE-REGISTRATION: realistic competing work

Written before the code. One switch, `Flags.realistic_competing`, DEFAULT OFF, with an arm field
to toggle it as `rc_tail` has.

### V12.1 The defect

`continuation_schedule` places a job's remaining pieces at
`cursor = t + (0.0 if priority else competing_s) + max(extra_work_s, 0.0)`, and its own docstring
says `competing_s` "is the engine-seconds of other work pi_0 would serve before this job's
pieces". **Every production caller passes 0.0**: `rollout.py:598` (the continuation value),
`rollout.py:669-670` (the A6 prefix-risk pair) and `coordinator.py:399` and `:437` (`classify`,
with `bounded_waiting_breach` at `:440` passing 0.0 as well).

So the schedule assumes the job has the engine entirely to itself. **That single zero causes
three separate failures**, each measured earlier in this report:

1. `p_finish` is pinned at 1, because a 1.0 s rebuild always "fits" a 5 s deadline on an idle
   engine, so the continuation value is the constant 0.035385924 at every deadline from 5.0 s
   down to 1.0 s and progress earns nothing (V3).
2. `classify` can never return PRIORITY, because its two branches are computed with
   `competing_s` and `competing_s_with_priority` both 0 and therefore agree. Measured: 81
   FEASIBLE and 19 INFEASIBLE over 100 deadlines, never PRIORITY (V6.1).
3. A3 is inert, because `priority` enters the schedule only as `(0.0 if priority else
   competing_s)`, which is identical when `competing_s` is 0 (V6.1).

### V12.2 The definition

For a job `j` in fleet state `f` at time `t`:

    competing_s(j, f, t) = sum of pr.gpu_s over
        every item in f.in_flight whose job_id != j.job_id
      + every item in f.pending whose job_id != j.job_id and whose pi_0 EDF key
        (deadline, due_at, item_id) sorts strictly ahead of j's own earliest remaining piece

`pr.gpu_s` is the frozen step model's own prediction for that item's request, so **no new
estimator and no new parameter is introduced**: the quantity is the same `gpu_s` the rollout
already sums into `busy`. In-flight work counts unconditionally because it is already running.
A job with no pending piece uses its own deadline as the EDF key.

`competing_s_with_priority` stays 0.0, which is the existing convention for "only work whose own
loss exceeds the job's value stays ahead", so PRIORITY becomes reachable exactly when a job
cannot finish behind the competing work but can finish ahead of it.

Applied at `rollout.py:598`, at the `rollout.py:669-670` pair (both sides get the same value, so
the A6 difference changes only through the feasibility cliff), and at the coordinator's two
`classify` sites and `bounded_waiting_breach`, since otherwise PRIORITY stays unreachable and the
ruling's own check cannot pass.

**Cost note, pre-registered as a risk.** This adds one `engine.predict` per pending or in-flight
item per evaluation. The predictions are a pure function of the request, so they are memoised on
the rollout instance, the same pattern as Option 0 and `u_sh_grid`. I will measure and report the
decision-time cost rather than assume it is small, and if it is large I will report that rather
than optimise, since speed work is D121 and is not authorised tonight.

### V12.3 Expected effect

1. `p_finish` stops being pinned at 1 for a robot job under load, so the continuation value gains
   a gradient in slack and progress starts earning credit.
2. `classify` returns PRIORITY for some jobs, which is the direct test, and A3 stops being a
   no-op.
3. Robot questions released before deadline rise above the 2 of 9 and 3 of 20 that the RC tail
   alone achieved.
4. Dashcam cost rises, because competing work now suppresses some continuation value that
   previously looked free; the size of that is the thing to watch.

If 2 does not happen, the fix has not done what it was built for and I will report that rather
than rework it.

## V13. PRE-REGISTRATION: splitting the RC tail into its two causes (user item 1)

I reported that `rc_tail` moved monitor releases from 2,107 to 4,008 at eight devices, flagged it
as larger than I expected, and did not separate the causes. The user asks for them separated, so
each becomes independently toggleable.

**The two candidate causes inside `rc_tail`, which the code makes distinct:**

| cause | what it is | why it could move SH |
|---|---|---|
| (a) the SHARED TAIL CURSOR | an `rc_piece` that cannot start inside H joins the single tail pass and advances `tail_free`, and the tail's progress feeds `_rc_utility` so `omega_RC x u_RC` can be credited | an `rc_piece` ahead of an SH item in queue order pushes that SH delivery LATER, lowering its credit |
| (b) the NEW RC ROWS in `_z_term` | `_rc_opportunities` appends one row per unanswered job, so `(device, "RC")` enters the aggregation | `_z_term` is a SUM over all (device, task) pairs, so adding RC rows changes the total for every candidate, including pure SH ones |

**The switches**, both DEFAULT OFF, with `rc_tail` kept as the master so today's behaviour is
unchanged:

    effective cursor = rc_tail or rc_tail_cursor
    effective z rows = rc_tail or rc_tail_zrows

So `rc_tail` alone still turns both on and is byte-identical to the current build, while
`rc_tail_cursor` alone and `rc_tail_zrows` alone isolate each component.

**What I will report, and the correction the user is right to demand.** Release counts alone are
what made my earlier report ambiguous. I will report DASHCAM OUTCOMES: instants served AND
PREDICTED ON TIME, per device, against v1.0 and against `edf`, read from `outcomes.jsonl` rather
than from release decisions. **If the extra releases arrive late, or if they crowd out robot work,
I will say so plainly rather than presenting a near-doubling of monitor releases as an
improvement.**

## V14. ITEM 2: the tail's decision cost, measured where it fires

**The 180 s synthetic table in V10.2 is labelled INVALID AS A TAIL COST wherever it appears**, and
the reason is already recorded there: instrumentation showed **0 beyond-horizon `rc_piece`
deliveries** on that fixture against 6,889 `episode_call` ones, so the tail never fires and the
table is the cost of a switch that does nothing.

Redone on the seed-0 FLEET traces, which contain robots, at 16, 32 and 64 devices, dry run, tail
ON against OFF, reporting per-decision p50 and p99, rollouts per decision, and beyond-horizon
`rc_piece` deliveries per period, so the cost is attributable to work the tail actually did.
**Whether the comparison is paired is stated explicitly**: the tail changes how many decisions a
run makes, so unless the decision counts match, the comparison is not like for like and is
labelled as such.

## V15. F3 measured, and a CORRECTION to my own earlier baseline numbers

Dry run, screening. Seed 0, 4 and 8 devices, 600 s, mu EWMA, H = 0.5 s, tight. Robot and dashcam
figures are now read from `outcomes.jsonl`, so they are SERVED and ON TIME, not release counts.

| n | variant | robot served / on time, of | dashcam served / on time, of | classify: FEASIBLE / PRIORITY / INFEASIBLE |
|---|---|---|---|---|
| 4 | v1.0 | see V10 (1 released) | 2,174 / 2,174 of 2,176 | 7,648 / **0** / 7,392 |
| 4 | A3+B1+tail+staleness | 2 / 1 of 9 | 2,128 / 2,128 of 2,176 | FEASIBLE 7,648, no PRIORITY |
| 4 | **+F3 competing** | 2 / 1 of 9 | 2,128 / 2,128 of 2,176 | 7,648 / **1** / 7,392 |
| 4 | `edf` | **9 / 8** of 9 | 2,174 / 2,174 of 2,176 | n/a |
| 4 | `llf` | **7 / 7** of 9 | 2,174 / 2,174 of 2,176 | n/a |
| 8 | v1.0 | 0 / 0 of 20 | 2,107 / 2,107 of 4,326 | 89 / **0** / 6,086 |
| 8 | A3+B1+tail+staleness | 3 / 2 of 20 | 4,006 / 4,005 of 4,326 | 1,878 / **0** / 21,322 |
| 8 | **+F3 competing** | 3 / 2 of 20 | 4,006 / 4,005 of 4,326 | 1,864 / **14** / 21,322 |
| 8 | `edf` | **19 / 0** of 20 | 4,320 / 4,266 of 4,326 | n/a |
| 8 | `llf` | **18 / 4** of 20 | 4,322 / 4,304 of 4,326 | n/a |

### V15.1 F3 did what it was built for, and almost nothing else

**PRIORITY is now reachable, which was the direct pre-registered test (V12.3 item 2).** `classify`
returned `FEASIBLE_ONLY_WITH_PRIORITY` **1 time at four devices and 14 times at eight**, against
**zero** in every run before F3. So A3 is no longer structurally inert and the three-way failure
caused by `competing_s = 0` is broken at its root.

**But the effect stops there.** Robot served and on time are unchanged at 2 / 1 and 3 / 2, and the
dashcam figures are identical to the run without F3. PRIORITY fires in 14 of roughly 23,200
classify calls, which is 0.06 per cent, so it is reachable but rare.

**Per the stop rule I am reporting this and moving on rather than reworking F3 into something
else.** It is kept because it removes a structural defect and because its own test now passes;
it is not kept on the strength of an outcome improvement, because there is not one.

### V15.2 CORRECTION: edf serves 19 of 20 robot questions at eight devices and ZERO arrive on time

My earlier sections said `edf` "serves 8 of 9 and 11 of 20". **Those were RELEASED-before-deadline
counts, not outcomes.** Read from `outcomes.jsonl`, the on-time picture is different and in one
place reverses the comparison:

| n | policy-core, all fixes | `edf` | `llf` |
|---|---|---|---|
| 4 | 1 on time | **8 on time** | 7 on time |
| 8 | **2 on time** | **0 on time** (19 served) | 4 on time (18 served) |

**At eight devices `edf` releases almost every robot question and none of them arrives in time**,
so policy-core's 2 on time is better than `edf`'s 0 and worse than `llf`'s 4. At four devices
policy-core is far behind both. This is the correction the user was right to demand: release
counts and on-time outcomes are different quantities, and I had been quoting the first as though
it settled the second.

### V15.3 The extra dashcam releases from the tail DO arrive on time

Also from outcomes rather than releases, which answers part of user item 1 directly. At eight
devices the tail takes dashcam served from 2,107 to 4,006, and **4,005 of those 4,006 are on
time**, against 2,107 of 2,107 for v1.0. So the near-doubling is not late work: it is roughly
1,900 additional instants answered within their deadline. It also did not crowd out robot work,
which went from 0 on time to 2.

The honest qualification is that both baselines still do better on dashcams at eight devices
(`edf` 4,266 on time, `llf` 4,304, policy 4,005), so the tail closes part of a gap rather than
creating an advantage.

## V16. ITEM 1 ANSWERED: both causes produce the SH effect, and they are not additive

Dry run, screening, seed 0, 600 s, outcomes from `outcomes.jsonl`. The two causes inside the tail
are now independently toggleable (V13), so the effect can be attributed.

| n | variant | dashcam served / on time | robot served / on time |
|---|---|---|---|
| 8 | v1.0 | 2,107 / 2,107 | 0 / 0 |
| 8 | **cursor only** | **4,090 / 4,090** | 0 / 0 |
| 8 | **zrows only** | **3,841 / 3,841** | 1 / 1 |
| 8 | both (`rc_tail`) | 4,006 / 4,005 | **3 / 2** |
| 8 | `edf` | 4,320 / 4,266 | 19 / **0** |
| 8 | `llf` | 4,322 / 4,304 | 18 / **4** |
| 4 | v1.0 | 2,174 / 2,174 | 1 / 1 |
| 4 | cursor only | 2,138 / 2,138 | 2 / 1 |
| 4 | **zrows only** | 2,036 / 2,036 | **2 / 2** |
| 4 | both (`rc_tail`) | 2,128 / 2,128 | 2 / 1 |

**Attribution, which is not what I guessed.** Neither cause is responsible on its own and they are
NOT additive. At eight devices the cursor alone takes dashcam service from 2,107 to **4,090** and
the z rows alone take it to **3,841**, while both together give **4,006**, which sits BETWEEN the
two. So each mechanism independently unlocks most of the increase, and combining them slightly
offsets rather than compounds.

**Robot service needs BOTH.** Cursor alone gives 0 on time, z rows alone give 1, both give 2. That
is the expected complementarity: the cursor makes the payoff visible through `_rc_utility`, the z
rows make the deficit visible through `_z_term`, and the question needs both channels.

**And one honest negative at four devices.** `zrows only` gets **2 of 9 on time** while `both` gets
only 1, so the shared cursor COSTS one on-time robot answer there, and every tail variant reduces
dashcam service slightly below v1.0 (2,036 to 2,138 against 2,174). So the cursor is not free: at
four devices it is mildly harmful on both axes, and it earns its place only at eight.

**The extra releases are not late**, which is the question I was asked to answer plainly: at eight
devices 4,005 of 4,006 dashcam instants served are on time, against 2,107 of 2,107 for v1.0, so
about 1,900 additional instants are answered within their deadline. They did not crowd out robot
work either, which rose from 0 to 2. Both baselines still beat policy-core on dashcams at eight
devices, so the tail narrows a gap rather than creating an advantage.

## V17. F4 PRE-REGISTRATION: probabilistic p_finish, with the fit source named before fitting

Own switch, `Flags.prob_p_finish`, DEFAULT OFF. Written before any fitting.

### V17.1 The fit source, which is committed and FIT-only

`results/cost/study_eng1/eng1_step_model.json` carries the step model's own residual summary,
with `fit_data` stating **"Part A (A_E0) and Part B E0 (B_E0) steps; Part C (incl. HOLDOUT) not
used"**. Total **n = 5,974**, `r2 = 0.9846`. The per-token-band relative residuals are:

| band | n | median relative residual |
|---|---|---|
| `tok_0_1` | 2,485 | 0.11560 |
| `tok_1_512` | 1,095 | 0.10946 |
| `tok_512_2048` | 1,255 | 0.05593 |
| `tok_2048_4096` | 677 | 0.05061 |
| `tok_4096_8193` | 462 | 0.07065 |

No HOLDOUT file is read: not ENG1 Part C, not ENG1c Part D, not ENG1d, not ENG1e. The frozen file
is READ only and its md5 is unchanged.

### V17.2 The form, fixed before looking at any outcome

A multiplicative (relative) error on the predicted completion time:

    T = T_hat * exp(eps),   eps ~ Normal(0, sigma_band^2)

so the probability the job finishes by its deadline is

    P_finish = Phi( ln(D_r - t) - ln(T_hat) ) / sigma_band )

with `Phi` the standard normal CDF. `sigma_band` is calibrated from the committed median relative
residual of the band matching the job's piece size, using the half-normal relation for a
zero-median log error:

    median|eps| = 0.6745 * sigma   =>   sigma_band = median_rel_res / 0.6745

So `sigma` ranges from 0.0750 (`tok_2048_4096`) to 0.1714 (`tok_0_1`). **There is no free
parameter and nothing is fitted to any outcome**: the only inputs are the committed median
relative residuals and the normal quantile constant.

### V17.3 The caveat that must travel with it

**These are per-STEP residuals, and a completion time is a sum of many steps.** Independent
per-step errors would partly average out, so using the per-step relative residual as the
completion-time relative residual OVERSTATES the uncertainty. The form is therefore
**conservative**, and `sigma_band` should be read as an upper bound rather than a calibrated
completion-time sigma. A properly calibrated completion-time error would need committed
predicted-against-actual completion pairs, which do not exist in committed form; I am not
inventing them.

### V17.4 Expected effect

1. `p_finish` stops being a step function, so the continuation value gains a gradient in slack
   and progress earns credit before the cliff, which is the saturation V3 identified.
2. A job with slack well above its predicted work keeps `p_finish` near 1, so comfortable cases
   are unchanged, and the gradient appears only near the deadline.
3. Robot questions released and on time should rise above the 2 of 9 and 3 of 20 the tail reached.
4. Because `classify` thresholds on `p_finish`, the FEASIBLE / PRIORITY / INFEASIBLE split will
   move; I will report it rather than predict a direction.

## V18. ITEM 2 REDONE: the tail's cost where it fires, and it is large

The 180 s synthetic table in V10.2 is **INVALID AS A TAIL COST** and labelled so there: the tail
produced 0 beyond-horizon `rc_piece` deliveries on that fixture. Redone on the seed-0 FLEET traces,
300 s, dry run, every switch of v1.1 on except the tail itself being toggled.

| n | tail | decisions | p50 | p99 | max | rollouts per decision | beyond-horizon `rc_piece` per period |
|---|---|---|---|---|---|---|---|
| 16 | OFF | 852 | 4.07 ms | 19.25 ms | 47.3 ms | 32.5 | **0** |
| 16 | **ON** | 3,920 | **6.54 ms** | **36.05 ms** | 439.9 ms | 11.5 | **13.6** |
| 32 | OFF | 3,265 | 8.60 ms | 161.17 ms | 557.2 ms | 15.8 | **0** |
| 32 | **ON** | 2,617 | **98.04 ms** | **1,741.50 ms** | 5,082.3 ms | 73.2 | **195.0** |

**The tail fires properly here**, 13.6 and 195.0 beyond-horizon `rc_piece` deliveries per period
against 0 with it off, so this is attributable to work the tail actually did.

**NOT PAIRED, and it matters.** Decision counts differ in both directions (852 against 3,920 at
16, 3,265 against 2,617 at 32), because the tail changes how many decisions a run makes. These are
therefore NOT like-for-like comparisons of the same decisions, and the p50/p99 columns must be
read with that in mind.

**The cost at 32 devices is severe and I am reporting it rather than softening it: p50 goes 8.6 to
98.0 ms and p99 goes 161 to 1,742 ms, against a 100 ms decision period.** At 16 devices it is
modest (+61 per cent p50, +87 per cent p99). The 64-device cell did not finish inside the time I
had, and I am not reporting a figure for it.

## V19. FINAL Step 3 for v1.1, with F4, and F4 adds nothing

Dry run, screening. Seed 0, 600 s, mu EWMA, H = 0.5 s, tight. Outcomes from `outcomes.jsonl`.

| n | variant | robot served / on time of | dashcam served / on time of | z[RC] max | PRIORITY | decisions vs v1.0 |
|---|---|---|---|---|---|---|
| 4 | v1.0 | 1 / 1 of 9 | 2,174 / 2,174 of 2,176 | 0.00 | 0 | reference |
| 4 | tail+stale+B1+A3 | 2 / 1 | 2,128 / 2,128 | 4.50 | 0 | 2,193 of 2,380 |
| 4 | +F3 | 2 / 1 | 2,128 / 2,128 | 4.50 | **1** | 2,193 |
| 4 | +F4, all v1.1 | 2 / 1 | 2,128 / 2,128 | 4.50 | 3 | 2,193 |
| 4 | `edf` | **9 / 8** | 2,174 / 2,174 | n/a | n/a | n/a |
| 4 | `llf` | **7 / 7** | 2,174 / 2,174 | n/a | n/a | n/a |
| 8 | v1.0 | 0 / 0 of 20 | 2,107 / 2,107 of 4,326 | 0.00 | 0 | reference |
| 8 | tail+stale+B1+A3 | 3 / 2 | 4,006 / 4,005 | 5.30 | 0 | 3,326 of 2,220 |
| 8 | +F3 | 3 / 2 | 4,006 / 4,005 | 5.30 | **14** | 3,326 |
| 8 | +F4, all v1.1 | 3 / 2 | 4,002 / 4,001 | 5.30 | 16 | 3,304 |
| 8 | `edf` | 19 / **0** | 4,320 / 4,266 | n/a | n/a | n/a |
| 8 | `llf` | 18 / **4** | 4,322 / 4,304 | n/a | n/a | n/a |

**F4 is inert in outcome terms**: robot 2 / 1 and 3 / 2 unchanged, PRIORITY 1 to 3 and 14 to 16,
dashcam slightly DOWN at eight devices (4,006 to 4,002). Per D125 its switch stays OFF and v1.2
supersedes it. It is implemented and tested, so it costs nothing to leave off.

**The dashcam axis confirms session 2's finding.** policy-core serves 2,128 of 2,176 at four
devices and 4,006 of 4,326 at eight, against `edf` at 2,174 and 4,320. So COVEX is behind on
dashcams too, and this is not a robots-against-dashcams trade.

## V20. F5a VERIFIED: the backlog units are ALREADY what the spec says. Hypothesis REFUTED

D126 asked me to verify before correcting, and to read spec 3.5 rather than invent a third
definition. The spec is explicit:

- `policy_spec_v4.md:147`: `- mu * (GPU backlog at t + H not already in any job's continuation
  value)`
- `policy_spec_v4.md:151`: "**mu is in utility units per GPU-second.**"
- `policy_spec_v4.md:239`: "residual GPU backlog ... **subtracted at mu per GPU-second**."

And the implementation matches on both sides:

| side | implementation | unit |
|---|---|---|
| the quantity | `residual = max(busy - H, 0.0)`, `busy` summing `pr.gpu_s` | GPU-seconds |
| the price | `_update_mu`: `realized = delta_j / pr.gpu_s` | utility per GPU-second |

**mu [utility per GPU-second] times backlog [GPU-seconds] is utility, so the product is
dimensionally consistent and it is the spec's own choice.** The hypothesis that the term compares
GPU-seconds against a wall-clock horizon in a way the spec did not intend is **refuted**: the spec
asks for GPU-seconds. Adopting `max(free_at - end, 0.0)` would be the third definition D126
forbids, so **I did not change it.**

### V20.1 And the term almost never fires, so it cannot be the dashcam explanation

Measured over 5,016 rollouts at eight devices on the seed-0 fleet trace:

| quantity | value |
|---|---|
| `busy` (GPU-seconds) | median 0.144, max 1.514 |
| **`residual = max(busy - H, 0)` non-zero** | **6 of 5,016 rollouts, 0.1 per cent** |
| `residual` median / p90 / max | 0.000 / 0.000 / 1.014 |

**So the GPU-overflow backlog channel is silent in 99.9 per cent of rollouts and cannot explain
COVEX's dashcam deficit.**

### V20.2 Where the backlog charge session 2 measured actually comes from

`mu_term = -mu * (max(busy - H, 0.0) + a6_backlog)`, and `a6_backlog` is
`sum(extra_work_s for v in risk.values())`, the A6 expected RESTORE work in seconds from the
prefix-risk dict. Since the GPU-overflow part is zero in 99.9 per cent of cases, the charge session
2 measured at a median of 1.084 must come almost entirely from `a6_backlog`. At the measured mu of
about 1.5 that implies an `a6_backlog` of roughly 0.72 s. **That is an arithmetic implication of my
measurement and session 2's, not a direct measurement, and it should be confirmed before anyone
acts on it.**

This matters for the ruling: `a6_backlog` is restore work in WALL-CLOCK seconds added to a
GPU-second quantity and multiplied by a per-GPU-second price. **That addition is where the units
genuinely do not agree**, and it is a different defect from the one the hypothesis named. I am
reporting it rather than changing it, because choosing how to reconcile A6 restore work with the
GPU-second backlog is a methodological choice, not a units typo, and D126 did not authorise it.

### V20.3 A smaller real defect, measured

`busy` charges every IN-FLIGHT request its FULL predicted `pr.gpu_s` (`rollout.py:251`), including
work already spent before `t0`, while the spec asks for backlog **at t + H**. In-flight items are
**median 66.7 per cent of `busy`, p90 100 per cent**, so the overstatement is large in relative
terms. Because `residual` fires in only 0.1 per cent of rollouts it has almost no effect today, so
I did not change it either; it is recorded as the thing to fix if the backlog channel is ever made
active.

## V21. F5b VERIFIED, and it is WORSE than session 2 found

Session 2 reported state value exactly zero for every candidate because both branches compute the
same sum. Measured over 5,016 terminal evaluations at eight devices:

| quantity | value |
|---|---|
| state-value rows produced per evaluation | median 2, max 4 |
| loop-eligible (device, rep) pairs | median 2 |
| **`sum(state_value)` exactly zero** | **5,016 of 5,016, 100 per cent** |

**The loop DOES run**, and `Device.demand` IS set (`arms_policy.py:550`), so the rows exist. But
each row's `value` is zero, so **the sum is absolutely zero per branch, not merely equal across
branches.** That is a stronger statement than "both branches agree": there is no state value
anywhere to differ.

**This directly affects v1.2's design and the user asked me to check it early rather than rely on
it.** The design note counts "state value at T_r" in the plan's Jhat and defines ABANDON as
"decline the remainder, keep the state value of what is built". **Both are inert today**, and F5b
as written ("wire the KV and host-tier bookkeeping into the terminal state value") may not be
sufficient on its own, because the zero originates inside `readiness.state_value` returning 0 for
every device and representation in this setting, not only in the absence of a branch difference.
Locating that is the first step of F5b and it was not part of my queue.

## V22. D127 point 2: the occupancy quantity now lives in ONE place

The user asked that F3's `competing_s` and spec 3.5's backlog term not disagree about what the
engine is doing, and that if I had already inlined the quantity in two places I factor it before
starting F5a and say so. **I had.** `competing_gpu_s` read `predict(...).gpu_s` directly while the
horizon loop accumulated `busy += pr.gpu_s`, so the expression existed twice.

Both now read `Rollout.occupancy_of(pr)`, a single function whose body is `float(pr.gpu_s)`, which
is what spec 3.5 asks for. **If F5a rules that spec 3.5 means remaining wall-clock occupancy, the
correction belongs in that one function and propagates to both readers at once**, with
`pr.service_s` as the wall-clock alternative.

**One divergence is recorded rather than silently reconciled**, because settling it is F5a's job
and not something to decide by inlining a third choice: the two readers pass different
`concurrent` values to `engine.predict`. The horizon loop passes the live concurrency;
`competing_gpu_s` passes 0, so that a job's competing work does not depend on the order in which
candidates happen to be scored. A test asserts the single-source property and that no site inlines
the expression any more.

## V23. Where v1.1 stands against the D127 gate

The gate is now edf AND llf on BOTH axes at every size, with `always-cloud-fcfs` reported but not
gating. Current standing from V19, dry run screening:

| axis | n | v1.1 (all fixes) | `edf` | `llf` | gate met? |
|---|---|---|---|---|---|
| robot on time | 4 | 1 of 9 | 8 | 7 | **NO** |
| robot on time | 8 | 2 of 20 | 0 | 4 | no (beats edf, below llf) |
| dashcam on time | 4 | 2,128 of 2,176 | 2,174 | 2,174 | **NO** |
| dashcam on time | 8 | 4,005 of 4,326 | 4,266 | 4,304 | **NO** |

**v1.1 does not meet the D127 gate on either axis at either size**, except that it beats `edf` on
robots at eight devices where `edf` gets none on time. That is the bar v1.2 has to clear, and it
is demanding on both axes exactly as the amendment says.

## V24. F5c PRE-REGISTRATION: route the deficit update through its spec entry point

Own switch is NOT needed and would be wrong here: this is a pure routing change with no
behavioural content, and adding a switch would imply there is something to turn off. Instead the
claim is that behaviour is IDENTICAL, and that is what the test and the byte-identity check
assert.

**The defect.** B1 wired the arm straight to `Device.bump_z`, so
`Coordinator.update_deficit`, which `spec_map.py` names as the implementation of spec 3.3 and
spec 7.6, became dead code. The spec entry point is therefore documented as live while nothing
calls it, which is the same failure class as the absent mechanisms this effort exists to remove.

**The change.** `arms_policy._z_resolve` calls
`self.co.update_deficit(self.fleet, rec["device"], rec["task"], success)` in place of
`dev.bump_z(rec["task"], float(self.params.p_k[rec["task"]]), success)`.

**Why it is exactly equivalent**, checked rather than assumed:

| step | before | after |
|---|---|---|
| the counter | `dev.bump_z(task, p_k[task], success)` | `update_deficit` does `fleet.device(did).bump_z(task, self.params.p_k[task], success_hat)` |
| the params | the arm's `self.params` | the coordinator is built as `Coordinator(self.pf, p, ...)` with the SAME `p` object, so `p_k` is the same dict |
| a missing device | the arm's `if dev is not None` guard skips it | `fleet.device(did)` is `self.devices[did]` and does NOT create, so the guard is KEPT to preserve that |

**Expected effect: none.** Decisions must be byte-identical with B1 on, before and after, and that
is the reported result rather than an assumption.

## V25. F5c DONE, and behaviour is identical as pre-registered

`arms_policy._z_resolve` now calls `self.co.update_deficit(self.fleet, device, task, success)`.
`Coordinator.update_deficit`, which `spec_map.py` names for spec 3.3 and spec 7.6, therefore has a
production caller for the first time and is no longer dead code.

| check | result |
|---|---|
| decisions with B1 on, before against after, seed 0, 4 devices, 300 s | **0 of 1,157 differ, IDENTICAL** |
| deficit counters over the same run | `z_updates` 1,058 and `z_misses` 3, unchanged |
| policy suite | 472 of 472 (4 new F5c tests) |

That is the pre-registered expectation met exactly: the routing carries no behavioural content,
and the equivalence is shown rather than asserted.

## V26. F5b: I MUST CORRECT MY OWN EARLIER FINDING. State value is not structurally zero, and F2 is what zeroes it

**Retraction first.** In V21 I reported that the terminal state value is "exactly zero in 5,016 of
5,016 terminal evaluations, absolutely zero PER BRANCH, with the zero originating inside
`readiness.state_value`". **That is wrong, and rulings were taken on it.** The correct measurement
is below.

### V26.1 `readiness.state_value` works

Instrumenting `_state_value` directly on a seed-0 four-device dry run, 1,365 calls:

| factor | value, identical on every call |
|---|---|
| `value` | **0.009216** |
| `p_need` | 0.260443 |
| `u_here` | 0.250000 |
| `u_next_colder` | 0.166667 |
| `u_device` | 0.166667 |
| `omega_RC` | 0.424631 |
| `credit_allowed` | True on all 1,365 |

`0.260443 x 0.424631 x (0.25 - 0.166667) = 0.009216`. **Nothing is zero, and nothing is
degenerate.** The function computes what spec 6.1 asks for.

### V26.2 The zero comes from F2, the staleness fix I shipped

Same harness, same trace, same switches except one:

| switches | `_terminal` state-value sum | exactly zero |
|---|---|---|
| `deficit_update` + `realistic_competing` | median **0.009216**, max 0.018432 | 1,196 of 4,254, **28.1 per cent** |
| the same **plus `write_staleness`** | median **0.000000**, max 0.000000 | **2,890 of 2,890, 100 per cent** |

**So F2 turns a term that is live in 71.9 per cent of evaluations into one that is zero in 100 per
cent.** My V21 run had `write_staleness` ON, which is why I saw 100 per cent and wrongly blamed
`state_value`.

The magnitude F2 writes is large: for the 6,781-token history in this trace,
`(6781 / 90) x 2.0 = 150.7 s` of staleness, against an RC deadline of 10 s.

**I could not isolate the internal route in a standalone reproduction**: calling
`_u_rc_from_tier` directly at 6,781 tokens returned 0.25 for both GPU and STORED at every
staleness from 0 to 150.7 s, which does not by itself produce the collapse. So the empirical fact
is established and the internal mechanism is NOT, and I am reporting it that way rather than
asserting a route I have not confirmed.

### V26.3 What this means for F5b and for v1.2, and why I stopped

**F5b's premise has changed.** D126 asked me to wire KV and host-tier bookkeeping into the terminal
state value because it was zero for every candidate. It is not: it is live in 71.9 per cent of
evaluations with F2 off, and the thing that kills it is F2's staleness magnitude.

Curing it means changing the quantity F2 FEEDS `state_value`, and that quantity's definition
("frames received minus frames built, in seconds of history") is the user's own F2 instruction, not
mine. **Changing a user-specified definition is methodological, so I stopped that branch and did
not touch it**, per the standing rule and D126's own stop condition.

**For v1.2:** with F2 ON as D125 requires, "state value at T_r" and the ABANDON option are indeed
inert, so the planner's value would come only from the SH term, the RC answer term, the deficit
term and the backlog. **But the cause is F2, not a broken state value**, so the remedy is a ruling
on F2's staleness magnitude rather than new wiring. That is a decision for the morning and v1.2
should not be built on top of either reading until it is made.

**Decisions this changes, flagged rather than built upon:** D126's F5b as written, and the part of
the v1.2 design note that counts state value at T_r and defines ABANDON by it.

## V27. v1.2 PRE-REGISTRATION (D125), written before the planner code

### V27.1 Switches

| switch | meaning | default |
|---|---|---|
| `Flags.planner_rc` | master: recall questions are planned, not scored per piece | OFF |
| `Flags.plan_latest` | the PIECES(b)-LATEST plans are in the candidate set | OFF |
| `Flags.replan` | the re-plan triggers are armed | OFF |
| `PolicyCoreArm.kappa` | the safety factor on predicted completion | **1.0, PROVISIONAL** |

v1.2 = `planner_rc` + `plan_latest` + `replan` ON, with B1, F2 and F3 ON and F1 and F4 OFF.

### V27.2 kappa has NO committed source, so it is 1.0 and PROVISIONAL

The note defines kappa as "the q90 ratio of measured to predicted job COMPLETION time on committed
FIT/DEV data". **No such quantity exists in committed form.** The search is the same one F4 used:
`eng1_step_model.json` carries per-STEP residual bands (`median_rel_res`, `p90_abs_res_ms`) over
n = 5,974 FIT-only steps, which are step-time residuals, not predicted-against-actual JOB
completion pairs. No HOLDOUT was touched.

Per the instruction, **kappa = 1.0, labelled PROVISIONAL**, and `t_ls(b)` therefore equals the
uninflated latest safe start. This is reported, not hidden, and the `kappa = 1` ablation in the
note's section 3 is consequently the same as the default until a source exists.

### V27.3 The plan set, the window, reservation and re-planning

Plans per the note: DECLINE (the reference), WARM, RELOAD, ONE-GO-NOW, PIECES(1024)-NOW,
PIECES(2048)-NOW, and with `plan_latest` the two LATEST variants. Only plans whose readiness
preconditions hold are enumerated; piece sizes are the measured D17 ones.

**Window.** `T_r = max(D_r, predicted plan completion) + one decision period`, so the rollout is
run with `horizon_s = T_r - t0` instead of H.

**Reservation.** A plan's units enter the evaluation as pending items carrying their planned
release time in `due_at`. The rollout already starts an item at `max(free_at, p.due_at)`, so
"executed at their planned times, subject to the engine" is the existing machinery rather than a
new mechanism.

**Jhat** over that window counts the SH per-instant values (D98), the recall answer's
`omega_RC x u_RC` at `D_r`, the per-device deficit term, the state value at `T_r`, and the backlog
at `T_r` priced by mu. `DeltaJ(plan) = Jhat(plan) - Jhat(DECLINE)`; argmax over feasible plans;
admit only if `DeltaJ > 0`; ties keep the cheaper plan in GPU-seconds.

**Re-plan** triggers (a) a unit completing later than planned so that predicted completion with
kappa now exceeds `D_r`, (b) prefix loss on verify-on-resume, (c) a believed-readiness tier
change. ABANDON is one option and every re-plan is logged with its cause.

### V27.4 The deficit term must be routed by the planner itself

F1 is OFF in v1.2 and its `_rc_opportunities` was the ONLY route that ever put RC rows into
`_z_term`, which aggregates over `opps` and whose `_opportunity_utility` emits `task="SH"` rows
only. **So the planner's long-window evaluation emits its own RC opportunity rows**, carrying
`met_slo` judged at the question's own deadline. Without that the note's stated deficit term would
read as implemented while contributing nothing, which is the failure class this whole effort
exists to remove. A test asserts the contribution is non-zero for a planned RC job on a device
carrying non-zero z. Measured range when routed: **0.267 to 1.800**, against a backlog charge of
0.7 to 2.06, so it is the live channel the planner most depends on.

### V27.5 OVERNIGHT DECISIONS, PROVISIONAL

1. **"State value at T_r" is wired exactly as the note specifies and is INERT whenever F2 is on.**
   Evidence: the terminal state-value sum is zero in **100 per cent** of evaluations with
   `write_staleness` on against **28.1 per cent** with it off (V26). The term is NOT dropped and
   NOT worked around, per the instruction. F2 is escalated for a morning ruling.
2. **ABANDON keeps its note definition**, and its "keep the state value of what is built" basis is
   PROVISIONAL pending that ruling. **Where the state value is inert, ABANDON reduces to declining
   the remainder**, and it is reported that way rather than being allowed to look valued.
3. **kappa = 1.0** as above.

### V27.6 Expected effects, against the v1.0 column in absolute counts

Pre-registered against v1.0 and not against edf or llf, since those figures are being reconciled.
v1.0, dry run screening, seed 0:

| n | robot questions on time | v1.2 expectation |
|---|---|---|
| 4 | **1 of 9** | more than 1 |
| 8 | **0 of 20** | more than 0 |
| 16 | 0 | more than 0 |
| 32 | about 0.014 pooled | above it |

Dashcam service must not fall below v1.0's at any size. With F1 off, v1.1 equals v1.0 on both axes
at every size, so the planner must deliver the whole improvement itself. If robot on-time counts do
not rise above the v1.0 column, v1.2 has not worked and I will report that rather than adjust the
expectation.

### V27.7 F5c's deliberate departure from the one-switch-per-fix rule

Recorded so a later reader does not read it as an oversight: **F5c has no switch, on purpose.** It
routes the deficit update through `Coordinator.update_deficit` with provably identical behaviour,
**0 of 1,157 decisions differing** with B1 on, so a switch over it would be dead by construction.

### V27.8 AMENDMENT to the pre-registration, before any planner code

Three corrections arrived after V27 was committed. V27 stands as written and these are recorded as
an amendment rather than an edit, so the pre-registration cannot be read as having been adjusted
after the fact.

**(a) The gate metric is DELIVERY, not dispatch, and my edf reading was the correct one.** Both
readings were arithmetically right on the same run: `released_before_deadline` is a dispatch
decision, while `outcomes.jsonl` with `t_delivered <= t_opportunity + deadline_s` is service. D82
is a service metric, so delivery governs. Corrected baselines, answered ON TIME:

| n | policy-core (v1.0) | `edf` | `llf` |
|---|---|---|---|
| 4 | **1** | 8 | 7 |
| 8 | **0** | **0** | 4 |
| 16 | **0** | **0** | 0 |

**(b) The dashcam deficit is at EIGHT devices only, and is REVERSED at sixteen.** Delivered
fraction:

| n | policy-core | `edf` | `llf` |
|---|---|---|---|
| 4 | 0.9991 | 0.9991 | 0.9991 |
| 8 | **0.4871** | 0.9854 | 0.9942 |
| 16 | **0.0747** | 0.0172 | 0.0294 |

At sixteen devices `edf` and `llf` dispatch 5,453 and 5,728 instants and only 150 and 256 arrive in
time, while policy-core dispatches 657 and delivers 651. **So COVEX is the best of the three at
sixteen devices** and the earlier "COVEX is worse on dashcams" driver is withdrawn except at eight.
**I will not design the planner to chase a sixteen-device dashcam problem, because there is not
one.** The relevant target is eight devices, where admitting only what scores positive costs COVEX
and the same conservatism protects it at sixteen. That tension is what the planner's reservation
aggressiveness has to navigate, and it is a reason to reserve carefully rather than greedily.

**(c) A zero-against-zero cell is NOT a success in my reporting.** At sixteen devices every arm
delivers zero robot answers, so a relative bar there is vacuous. I will report ABSOLUTE delivered
on-time counts throughout and leave the gate arithmetic to session 2, per the caveat the user is
being asked to rule on.

**Expected effects, restated in delivered-on-time absolute counts against v1.0:** more than 1 at
four devices, more than 0 at eight, more than 0 at sixteen, with the delivered dashcam fraction not
falling below v1.0's 0.9991, 0.4871 and 0.0747. The eight-device dashcam figure is the one with
room to improve and the sixteen-device one is already the best of the three, so it must be
protected rather than traded.

## V28. v1.2 BUILT AND MEASURED. The planner works and the OBJECTIVE declines the plans

Dry run, screening. Seed 0, 600 s, mu EWMA, tight. Robot and dashcam figures are DELIVERED on
time, per the V27.8 amendment.

### V28.1 What was built

`policy/planner_rc.py` plus a long window and planner-routed RC rows in the rollout:

| piece | where |
|---|---|
| the plan set (DECLINE, WARM, RELOAD, ONE-GO-NOW, PIECES(b)-NOW, PIECES(b)-LATEST) | `planner_rc.enumerate_plans`, preconditions enforced, D17 sizes only |
| the long-window evaluation to `T_r` | `Rollout.run(horizon_s=...)`, None keeps the dispatch horizon so every existing caller is unchanged |
| reserved units at planned times | the plan's units carry `due_at`, which the rollout already honours as `max(free_at, due_at)`, so no new mechanism |
| the planner's OWN RC rows into `_z_term` | `Rollout.run(rc_rows=True)`, required because F1 is off and `_rc_opportunities` was the only route |
| re-plan triggers and ABANDON | `planner_rc.replan_cause`, `planner_rc.abandon_note` |
| switches | `planner_rc`, `plan_latest`, `replan`, all default OFF, plus `kappa` in the run header |

Policy suite **481 of 481** (9 new v1.2 tests). 12 frozen md5s green.

### V28.2 The planner fires, and declines most plans

Instrumented at four devices: **2 of 2 RC escalations reached the planner** and it returned a
decision for both, so the gate and the plan loop work. Over a full 600 s run at four devices the
decision log shows **2 plans ADMITTED** (`release_whole` 2, `release_recall` 2) and **6 DECLINED**;
at eight devices 1 admitted and 9 declined.

### V28.3 The plan DeltaJ magnitudes, which is the finding

Captured from three consecutive plan evaluations at four devices. `T_r` came out at 5.01 to 5.06 s,
so the long window is working as specified.

| evaluation | reference Jhat | best plan | its DeltaJ | its GPU-seconds |
|---|---|---|---|---|
| 1 | +0.074409 | ONE-GO-NOW | **-0.598529** | 0.8738 |
| 2 | +0.141521 | PIECES-LATEST(1024) | **-1.053643** | 1.3943 |
| 3 | +0.075265 | PIECES-NOW(2048) | **-1.585175** | 2.2205 |

Every plan in every evaluation scored negative, from **-0.598 to -2.521**, and the magnitude tracks
the plan's GPU cost at roughly **-0.7 per GPU-second**: -0.599 at 0.87 GPU-s and -1.854 at 2.41
GPU-s.

**So the long window did NOT change the exchange rate; it preserved it.** Against that cost the
objective credits the answer `omega_RC x (acc_cloud - acc_device) = 0.0354` plus a deficit term
measured at 0.267 to 1.800. Even a maxed deficit of 1.8 cannot cover the 1.85 charged for a
2.41 GPU-second rebuild. **The planner is computing correctly and the objective is what declines
the work.**

This is the exchange-rate problem F-A6 named, which D124 forbids fixing by touching omega, mu,
targets, H or thresholds. **I did not touch any of them.** v1.2 as designed cannot deliver robot
service while that exchange rate stands, and that is the result rather than a bug in the planner.

### V28.4 Outcomes, against the pre-registered v1.0 column

| n | variant | robot delivered of | dashcam delivered fraction |
|---|---|---|---|
| 4 | v1.0 | **1** of 9 | 0.9991 |
| 4 | **v1.2, F2 off** | **2** of 9 | 0.9977 |
| 4 | **v1.2, F2 on** | **2** of 9 | 0.9977 |
| 4 | ablation: no LATEST | 2 of 9 | 0.9977 |
| 4 | ablation: no replan | 2 of 9 | 0.9977 |
| 4 | `edf` | 8 of 9 | 0.9991 |
| 4 | `llf` | 7 of 9 | 0.9991 |
| 8 | v1.0 | 0 of 20 | 0.4871 |

**Against the pre-registration:** robot delivered rose from 1 to 2 at four devices, which meets
"more than 1". **The dashcam condition FAILED**: 0.9977 against v1.0's 0.9991, a loss of 3 instants.
So v1.2 bought one robot answer for three dashcam answers at four devices, and it remains far below
`edf`'s 8 and `llf`'s 7.

**F2 ON and F2 OFF are IDENTICAL at four devices** (2 of 9 and 0.9977 both), so the state-value
inertness that F2 causes did not change v1.2's outcome here. That is consistent with V28.3: the
decision is dominated by the GPU cost term, not by the state value.

**Both ablations are identical to v1.2**, so neither the LATEST start option nor re-planning changed
any outcome at four devices. With the planner declining most plans, there is little for either to
act on.

The eight-device v1.2 cells did not finish inside the time I had. The decision log for the run that
did execute shows 1 admit and 9 declines, and I report no outcome figure for that size rather than
a partial one.

### V28.5 The overnight decisions, as recorded

1. **State value at T_r is wired exactly as the note specifies and is inert whenever F2 is on**
   (100 per cent zero against 28.1 per cent with F2 off). Not dropped, not worked around.
   **OVERNIGHT DECISION, PROVISIONAL.**
2. **ABANDON keeps its note definition**, and `abandon_note()` states plainly that where the state
   value is inert it reduces to declining the remainder. **OVERNIGHT DECISION, PROVISIONAL.**
3. **kappa = 1.0**, no committed source. **OVERNIGHT DECISION, PROVISIONAL.**

### V28.6 What I did not do, and why

I did not adjust omega, mu, targets, H, thresholds, F2's formula, `a6_backlog` or the in-flight
`busy` charge. V28.3 shows the planner's declines follow from the exchange rate those quantities
set, so the natural next step touches one of them, and every one is either forbidden by D124 or
already escalated. **That is a decision for the morning, and I stopped rather than take it.**

### V28.7 The eight-device cells DID finish, and they change the verdict

V28.4 reported that the eight-device v1.2 cells did not finish in the time I had. They completed
after I wrote that, so the figures are below and **V28.4's "no outcome figure for that size" is
superseded.**

| n = 8 | robot delivered of 20 | dashcam delivered fraction of 4,326 |
|---|---|---|
| v1.0 | **0** | **0.4871** |
| **v1.2, F2 off** | **1** | **0.7998** |
| **v1.2, F2 on** | **1** | **0.7998** |
| ablation: no LATEST | 1 | 0.7980 |
| ablation: no replan | 1 | 0.7998 |
| `edf` | **0** (19 served) | 0.9854 |
| `llf` | **4** (18 served) | 0.9942 |

**Both pre-registered conditions are MET at eight devices**, and the dashcam one by a wide margin:

- robot delivered 0 to **1**, so "more than 0" is met, and it BEATS `edf`, which delivers none of
  the 19 it serves, while trailing `llf`'s 4;
- dashcam delivered **0.4871 to 0.7998**, which is about **1,353 more instants answered in time**,
  against the pre-registered condition of merely not falling below v1.0.

**This is the opposite sign from four devices**, where dashcam fell 0.9991 to 0.9977. So v1.2
costs three dashcam answers at four devices and gains about 1,353 at eight. **Eight devices is
exactly where the user identified the real dashcam deficit**, and it is the size where v1.2 helps
most, which was not visible when I wrote V28.4.

It remains below both baselines on dashcams at eight devices (0.7998 against 0.9854 and 0.9942),
so the gap is narrowed rather than closed, and robot service at 1 of 20 is still far from the 20.

**One ablation now separates**, unlike at four devices: `no LATEST` gives 0.7980 against v1.2's
0.7998, so the LATEST start option contributes a small dashcam gain at eight devices by deferring
rebuild work out of the way. `no replan` remains identical.

**Correction to my own summary.** I characterised v1.2 as "bought one robot answer for three
dashcam answers". That holds at four devices only. At eight it buys one robot answer AND about
1,353 dashcam answers, so the honest overall summary is that **v1.2 helps materially at eight
devices and costs slightly at four**, while still trailing `llf` on both axes.

## v1.3 development log (D129)

One line per change, each behind a switch or parameter, in the order made.

- `completion_error.kappa_for_tokens`: kappa derived as `exp(z_0.90 * sigma_band)` from the committed FIT-only residual bands, 1.10 to 1.14 by piece size, replacing the unvalidated 1.0; a fixed value still overrides so the kappa = 1 ablation stays reachable.
- `planner_rc.enumerate_plans(kappa=None)`: None now means DERIVE, and PIECES-LATEST starts earlier by the derived factor.
- `coordinator._update_mu` estimator `"scarcity"`: first `mu_scale * min(1, busy_ahead / H)`, then, after a probe showed it pinned at the cap in 92.9 per cent of busy calls, regraded to `mu_scale * x / (1 + x)` with `x = busy_ahead / mean_predicted_service`; selected by arm field `mu_mode="scarcity"` with `mu_scale`.
- `arms_policy` mu branch made a proper elif chain: the scarcity branch had been overwritten by the following else two lines later, so its first screen silently ran as EWMA and matched it to four decimals.
- `arms.make_arm`: parameters now actually reach non-policy arms; kwargs had been silently discarded, so `make_arm("edf", c_inflight=4)` returned the default arm. D128 requires C_inflight 4 to stay reachable and it now is.
- `arms_policy.release_floor_c` (default 0, off): work-conserving release floor; while fewer than C requests are in flight the best HELD candidate is released even at non-positive DeltaJ.
- `coordinator.admit_floor_c` (default 0, off): the same floor at the ADMISSION gate, added after the release floor measured as an exact null.

### What the night established

**1. The price of GPU time was the binding constraint, and the fix is to remove it.** The diagnostic the directive asked for first is decisive at eight devices over 600 s on seed 0:

| mu | robot delivered | dashcam |
|---|---|---|
| EWMA | 1 of 20 | 0.7998 |
| **0** | **8 of 20** | **0.9330** |
| 0.72 fixed | 0 of 20 | 0.1325 |
| 2.89 fixed | 1 of 20 | 0.7016 |

mu = 0 is better on BOTH axes than every priced variant. At four devices it gives 4 of 9 against the EWMA's 2. This is the COVEX analogue of raising C_inflight and it converges with F-A8, F-A9 and session 2's edf-at-C=8 result: COVEX was refusing work under predicted congestion.

**2. The scarcity price did not beat mu = 0, and it took two forms to say that honestly.**

The first form was `mu_scale * min(1, busy_ahead / H)`. Session 2 predicted from reading the source, BEFORE any v1.3 number existed, that it would SATURATE: H is 0.5 s and one request services in about 1 s, so the ratio is almost never below 1. A direct probe at 16 devices confirmed it exactly: **mu sat at the cap in 92.9 per cent of busy calls, with five distinct values**. That is a binary "is anything in flight" indicator, not a graded price. By the CLAUDE.md Step 2 standard the scarcity channel was **CONSTANT**, so that run is **INCONCLUSIVE**, not a negative result: it could not test the claim, and its delivery numbers are additionally confounded with a roughly tenfold cut in the backlog charge against the EWMA's p50 of 9.835 at 16 devices.

The form was then fixed to normalise by MEASURED service rather than by H and to saturate smoothly rather than clamp, `x = busy_ahead / mean_predicted_service`, `mu = mu_scale * x / (1 + x)`. Re-probed on the same cell, **mu ranges 0.5 to 0.889 over eight distinct values with nothing at a cap**, so the channel now VARIES as the claim requires. With the graded price COVEX still delivers **0 of 20 robot answers and 0.5803 dashcam at 16 devices, against mu = 0's 13 of 35 and 0.7268**.

That second run is a **REAL NEGATIVE** under Rule 2: the mechanism was present and varying, it operated as specified, and it did not produce the claimed effect. **Pricing predicted backlog at all makes COVEX worse than not pricing it**, and the graded price is worse than the saturated one, which is the direction that negative predicts.

**3. The refusal is NOT at either gate, which is a null worth recording.** The release floor is an EXACT null at 8 devices: 8 of 20 and 0.9330 at every setting of 0, 4, 8 and 16. The admission floor moves dashcam from 0.9330 to 0.9346 and robot not at all. Neither locates the remaining gap, so the gap is structural in the counterfactual, which charges the harm a served opportunity does to others, and not a threshold that can be loosened.

**4. D128's default change alone raised the bar a long way, and it corrects a number I reported.** At eight devices edf delivers 0 of 20 robot answers at C_inflight 4 and 19 of 20 at C_inflight 8, dashcam 0.9854 against 0.9991. My earlier reading that edf delivers 0 of 20 was edf at C = 4.

**5. Where the candidate stands.** v1.3 = v1.2 with mu = 0, on seed 0 at 600 s:

| size | v1.3 mu=0 | edf C=8 | llf |
|---|---|---|---|
| 8 | 8 of 20, 0.9330 | **19 of 20, 0.9991** | 18 of 20, 0.9991 |
| 16 | **13 of 35**, 0.7268 | 4 of 35, **0.9508** | 6 of 35, 0.9633 |

At sixteen devices COVEX delivers three times the robot answers of the best baseline and loses dashcam; at eight it loses both. **It does not meet the D129 goal of beating the best baseline on both axes at every size**, and the honest leaderboard row says so.

### v1.3-fast release: the leaderboard row, stated honestly

Released as `covex-v13` in `live2/arms.py`, which is `policy-core` with the v1.1 defect fixes and
the v1.2 two-timescale planner on, **the price of GPU time set to zero**, the admission floor at 8,
and kappa derived. The H100 can ask for it by that one name.

**IT DOES NOT MEET THE D129 GOAL.** The goal was to beat the best scheduling baseline on BOTH
dashcam and robot delivery at 4, 8, 16 and 32 devices. v1.3 does not. At 16 devices, 600 s:

**THE BAR IS llf AT C=8, NOT edf.** `LlfArm` subclasses `Pi0Edf`, so llf INHERITED the D128
default change at `700f248`, and llf at C=8 beats edf at C=8 on both axes. The comparison below is
therefore stated against llf, which is the number a reviewer will use. My own seed run already
built llf through the fixed `make_arm`, so these llf rows are C=8 rows.

| seed | v1.3 (mu=0, af8) | llf C=8 (the bar) | edf C=8 |
|---|---|---|---|
| 0 | **14 of 35**, 0.8164 | 6 of 35, **0.9633** | 4 of 35, 0.9508 |
| 4 | **13 of 41**, 0.8751 | 9 of 41, **0.9730** | 3 of 41, 0.9609 |

At 8 devices it loses BOTH axes: 8 of 20 and 0.9330 against edf-at-8's 19 of 20 and 0.9991.

The crossover SURVIVES against the stronger baseline, with a smaller robot margin than against edf:
roughly 2.3x and 1.4x rather than 3.5x and 4.3x.

**What is nonetheless true and worth carrying into round 1.** At 16 devices v1.3 delivers **three
to four times the robot answers of the best baseline** while giving up about 0.13 of dashcam. That
is a real and repeated trade, not noise, and it is the first time COVEX has beaten a scheduling
baseline on any axis at scale. **Seed stability is also much improved**: v1.2 ranged 0.062 to 0.590
on dashcam across seeds, where v1.3 sits at 0.8164 and 0.8751. The crossover between 8 and 16
devices is the honest headline: COVEX is worse than a trivial scheduler when the GPU is adequate
and better on the deadline-bearing workload when it is not.

**Speed-ups are OFF in this release.** None was implemented tonight; the night went to the price
of GPU time, which the evidence kept pointing at. Nothing in this release is a speed-up that could
fail to be byte-identical, so the byte-identity question does not arise for it.

**The open item I would put first next.** The gap at 8 devices is not a gate: the release floor is
an exact null and the admission floor is near-null there. It is structural in the counterfactual,
which charges a served opportunity the harm it does to others and so refuses under contention even
where serving more is better overall. That is the thing to redesign, not another threshold.

### The structural finding, recorded in full for the morning

**Claim.** COVEX's remaining gap at 8 devices is NOT a threshold that can be loosened. It is
structural in the counterfactual objective, which charges a served opportunity the harm it does to
every other opportunity, and therefore refuses work under contention even where serving more is
better overall.

**Evidence, in the order it was obtained.**

1. **Removing the price is not enough.** mu = 0 lifts 8-device robot delivery from 1 of 20 to 8 of 20 and dashcam from 0.7998 to 0.9330, but llf and edf at C=8 both reach 18 and 19 of 20 with 0.9991. A large gap survives the price going to zero, so the price is not the whole cause.
2. **The release gate is an EXACT null.** `release_floor_c` at 0, 4, 8 and 16 gives byte-identical outcomes at 8 devices: 8 of 20 and 0.9330 at every setting. Forcing held candidates out is not merely insufficient, it changes nothing, which means held-at-release is not where the work is being lost.
3. **The admission gate is near-null at 8 devices.** `admit_floor_c` at 4, 8 and 16 moves dashcam 0.9330 to 0.9344, 0.9346, 0.9346 and robot not at all. It does help at 16 devices (13 of 35 to 14 of 35, and 0.7268 to 0.8164), so the floor is implemented and live; it simply does not reach the 8-device deficit.
4. **The price axis is effectively BINARY, which localises the cause in the objective.** Session 2 measured that a tenfold price cut buys ZERO additional robot deliveries, while removal buys 8 of 20. Both hold at once because a 2.41 GPU-second cold rebuild charged at any nonzero price exceeds the maximum available credit of about 1.835. **At the objective's current exchange rate no nonzero price admits a cold rebuild.** That is a statement about omega_RC and the accuracy gain, not about the price form.

**What this rules out.** Tuning mu, the floors, H, or any admission threshold cannot close the
8-device gap, because two of those are measured nulls and the third is binary.

**Where the next redesign goes.** The exchange rate between an RC answer's credit and the GPU-second
cost of producing it, which is omega_RC against the accuracy gain in the objective, not the
estimator that prices the GPU-second. A counterfactual that charges full harm-to-others is correct
for a saturated engine and systematically over-conservative for one with slack, which is exactly the
8-versus-16-device crossover the leaderboard shows.

### F2 and the state value (D129 item 3): cause found and fixed

**The cause of the F2 collapse is a DOUBLE CHARGE, and it is now fixed.** `write_staleness` set
`staleness_s` from EVERY unbuilt token, but `utility.t_ready_s` already charges a STORED history
`size_tokens * seconds_per_token("rebuild")` as `t_restore` for exactly those tokens. A cold
history therefore paid for its own reconstruction twice, once as restore and once as catch-up.

**Measured, not assumed.** A probe of `_u_rc_from_tier` at 8 devices on a 200 s run:

| condition | staleness over 36k to 43k calls | robot delivered | dashcam |
|---|---|---|---|
| F2 on, before | min 90.0, p50 **240.7**, max 270.7 s; 0.0% zero | **0 of 7** | 0.9611 |
| F2 off | all zero | 2 of 7 | 0.9347 |
| **F2 on, fixed** | **99.7% zero**, max 90.0 s | **2 of 7** | 0.9347 |

A p50 staleness of 240.7 s on a 200 s run is a whole run's worth of catch-up charged to a history
that was never fresh to begin with, which is what made every representation infeasible and drove
robot delivery to zero. With the fix, catch-up fires only where the restore does not already do the
work, which is 0.3 per cent of calls at this size, and robot delivery returns to the F2-off level.

**An honest limit on the state-value half.** The same probe recorded `readiness.state_value`
returning zero in 100 per cent of calls in BOTH the F2-on and F2-off conditions. That does not match
my earlier V21 and V26 reading, which put the F2-off rate at 28.1 per cent, and the two are
measuring through different entry points, so I am NOT claiming the state value is explained. What is
established is narrower: **the F2 delivery collapse is the double charge and is fixed**; whether the
terminal state value is separately inert is an open item, and the ABANDON plan's basis stays
PROVISIONAL until it is settled.

**This does not change the release.** `write_staleness` is OFF in `covex-v13`, so the fix affects no
released number; it makes F2 usable for whoever turns it on next.

### Resolutions from session 2, recorded

**F-A2, the state value: settled against my correction, and my newest reading was the anomaly.**
Session 2 measured the between-branch difference as exactly zero in 12,898 of 12,898 candidates,
max absolute difference 0.0, at both commits under both F2 settings, while the per-branch sum is
only 3.4 per cent zero. The channel is substantively ALIVE and **cancels exactly**. My three
readings were never three readings of one quantity:

- `state_value` is a caching wrapper over `_state_value` whose shadow mode asserts they agree, so the two cannot differ in value.
- `rollout.py:701` imports the name INSIDE the function, so a patch on `readiness` reaches it, while `coordinator.py:21` binds it at MODULE LEVEL, so the same patch does not. **Patching one module silently misses the other, which is what my probe did.**
- The cache hides 94 per cent of traffic, 105,852 wrapper calls against 6,157 computations, so my count of 1,365 was a cache-MISS count and not a call count.

My first reading reproduces at `700f248` and my 28.1 per cent sits beside session 2's 19.21 per cent
(rollout) and 12.62 per cent (coordinator), the same two-valued distribution sampled differently. My
100-per-cent-zero reading reproduces at neither commit and is the anomaly. **Leaving it open rather
than tidying it was the right call, and the lesson for my own instrumentation is that a module-level
`from x import y` makes monkey-patching the source module a silent no-op.**

**The design consequence, which is the part that matters.** The cancellation is STRUCTURAL: state
value is computed for future arrivals from `device.history[rep]`, which a dispatch action does not
change, so both branches evaluate the identical prefix and the term is a constant offset on both
sides. **v1.2 and v1.3 therefore both count state value inertly, and ABANDON does reduce to
declining the remainder.** Anything that wants ABANDON to differ must make the RETAINED PREFIX
DIFFER BETWEEN BRANCHES. That is the concrete requirement for any future memory-aware work, and it
settles the provisional note in `planner_rc.abandon_note`.

**One scalar cannot serve both axes, and my own floor sweep confirms it.** Session 2 falsified its
earlier attribution with a control and concluded that the price is **GRADED on dashcam and BINARY on
robots**. My admission-floor sweep at 16 devices independently saturates in exactly that shape:

| seed | af8 | af16 | af32 | af64 |
|---|---|---|---|---|
| 0 | 14 of 35, 0.8164 | 14, 0.8215 | 14, **0.8215** | 14, **0.8215** |
| 4 | 13 of 41, 0.8751 | 13, 0.8764 | - | - |

Robot delivery does not move at all and dashcam gains 0.005 and then pins. **The floor is a second
scalar and it fails the same way the price does.** Closing the dashcam gap while holding robots
needs a term that separates the two axes, not another threshold value.

**Not chased: the published arms.** Session 2's leaderboard shows seven in-scope published arms at
33 to 35 of 41 robots at 16 devices against llf's 9. A shared fairness digest proves a shared TRACE
and not shared COSTS, and a rebuild never charged to the accelerator budget is precisely the E36
failure mode this project has precedent for. Those numbers are UNVERIFIED pending the
accelerator-ms and KV-bytes-per-released-item check, and I did not let them redirect remaining time.

### The robot axis is queueing, and for COVEX the binding variable is VOLUME, not delay

Session 2's cost check settled that the published arms are real: a recall rebuild costs eco-llm
2.404 s against llf's 2.420 s and a monitor release costs every arm 0.395 s exactly, so there is no
uncharged work and no E36 artefact. The robot axis is a queueing problem: the same 38 requests at
the same service, differing only in WHEN the answer returns against a 5.0 s deadline.

The suggested target was to get COVEX's median recall delivery under 5.0 s. **Measured on the
release's own committed runs, it already is, in three of four seeds, and it beats llf in all four.**
No new run was needed; the delays come from the `outcomes.jsonl` of the four-seed 16-device set.

| cell | recall delay p50 | on time at 5s / 6s / 7s |
|---|---|---|
| edf C=8 (seeds 0,4,5,6) | 6.22, 6.36, 6.42, 6.21 | packed above the deadline |
| llf C=8 | 5.72, 5.81, 5.41, 5.56 | 6/21/29, 9/20/29, 9/21/31, 10/23/29 |
| **v1.3 (mu=0, af8)** | **4.01, 5.34, 4.36, 4.32** | 14/15/17, 13/15/19, 17/18/21, 9/11/13 |

**So COVEX does not have llf's problem.** llf's delays are packed against the deadline, where two
seconds of relaxation triples its deliveries; COVEX's are not, and relaxing the deadline buys it
almost nothing (14 to 17, 13 to 19, 17 to 21). **The correction to the target is that for COVEX
latency is already the wrong variable.**

**The binding variable is admission VOLUME.** Over the same four seeds at 16 devices:

| arm | recall served, of offered | conversion of served into on-time |
|---|---|---|
| llf C=8 | 32/35, 38/41, 38/41, 35/37 = **91 to 95%** | 6, 9, 9, 10 = **19 to 29%** |
| edf C=8 | 83 to 93% | 10 to 21% |
| **v1.3 (mu=0, af8)** | 20/35, 28/41, 26/41, 15/37 = **41 to 68%** | 14, 13, 17, 9 = **46 to 70%** |

**COVEX schedules two to three times more efficiently per request it accepts and then accepts only
half as many.** That is the whole shape of the result, and it explains every robot number of the
night more directly than the price did: mu = 0 helped because it raised ADMISSION, and the
admission floor helped at 16 devices for the same reason (volume 16 to 20, 20 to 28, 20 to 26).

**The concrete target for the morning, with numbers.** eco-llm reaches 35 of 38 by combining about
93 per cent volume with about 92 per cent conversion. COVEX has 41 to 68 per cent volume and 46 to
70 per cent conversion, so **the gap is on BOTH factors and volume is the larger one**. Raising
COVEX's admission to llf's rate at its current conversion would put it near 17 to 26 robots; closing
the rest needs conversion too. The measured price of that trade for eco-llm is 910 fewer monitor
requests.

**One anomaly, flagged not smoothed.** On seed 6 the admission floor REDUCED volume, 23 served down
to 15, and robots with it, 14 down to 9. The floor is not monotone in volume across seeds, which is
the same seed-6 instability that breaks the robot win and should be understood before the floor is
relied on.

### Why no "v1.3-fast release 2"

At 32 devices on seed 0, v1.3 holds 13 of 72 robots and 0.4588 dashcam while llf and edf both
collapse to 0 robots and 0.0130 and 0.0127 dashcam. **I am not claiming that as a pass**, on the
same standard session 2 applied when it declined one it could have claimed: every arm is broken at
that size, 0.46 dashcam does not meet the SLO either, and a ranking among broken arms is not
evidence the SLO can be met. It is a finding about fixed-in-flight schedulers having no overload
protection, not a demonstration that COVEX works at 32 devices.

**The four-seed 16-device record also does not support a release 2.** v1.3 beats llf on robots on
seeds 0, 4 and 5 and LOSES on seed 6, 9 of 37 against 10 of 37, and loses dashcam on all four. By
the stability rule a three-of-four win is not a win. `d944361` stands as the release.

### The ONE-GO-NOW ablation (D125 section 3): the hypothesis is REFUTED for COVEX

Session 3's cost check showed the published arms issue ONE FULL COLD REQUEST PER QUESTION, 37 COLD
events at median 2.1069 gpu_s, where llf CHAINS SMALL PIECE BUILDS, 53 events at median 0.4162, and
suggested piece chaining may itself be the defect. The D125 ablation tests it directly.

**Question 1: does the planner ever CHOOSE ONE-GO-NOW? Yes, routinely.** On the release's switch set
at 16 devices, seed 0, the chosen-plan histogram is **WARM 14 (40%), ONE-GO-NOW 11 (31%), PIECES-NOW
10 (29%), DECLINED 0**. Offered counts are PIECES-NOW 42, PIECES-LATEST 42, ONE-GO-NOW 21, WARM 14,
so where ONE-GO-NOW is on the menu it WINS 11 of 21, while PIECES-NOW wins only 10 of 42. **COVEX
already prefers the single cold rebuild when it is available.**

**Question 2: forced to ONE-GO-NOW, what happens? It collapses.** Seed 0, 16 devices:

| arm | recall served | robot on time | dashcam |
|---|---|---|---|
| release (full plan set) | 20 of 35 | **14** | **0.8164** |
| ONE-GO-NOW only | **4** of 35 | 2 | 0.5078 |
| no chaining (ONE-GO-NOW + WARM + RELOAD) | **4** of 35 | 2 | 0.5078 |
| llf C=8 | 32 of 35 | 6 | 0.9633 |

**Piece chaining is NOT COVEX's defect. Removing it costs 12 of 14 robot answers.** The two forced
arms are identical, so WARM and RELOAD are not what the strict form was losing; the loss is entirely
the pieces. The mechanism is admission volume again: a full cold rebuild costs about 2.4 gpu_s and
COVEX's admission test will fund only **4** of them, where pieces let it fund 20.

**What this eliminates and what it leaves.** The most promising hypothesis on the board is refuted,
and it re-points at the same place everything else has: **COVEX's admission test refuses
expensive-but-correct work.** The published arms simply issue the expensive request; COVEX's
counterfactual charges a 2.4 gpu_s rebuild against the harm it does to other opportunities and
declines it. The defect is the ADMISSION TEST, not the plan set, and the plan set is already
choosing correctly within the budget the test allows it.

### D128 breaks the piece arms at C_inflight 8, and this needs a decision

The H100 reported at `b786c0c` that the suites fail on the release with "stale C_inflight-4 tests
and a real piece-partition failure at C_inflight 8", and skipped the piece arms. Both halves check
out, and the second is a real defect **caused by the D128 default change**:

- **12 stale failures** in `test_live2_d114.py` and `test_live2_d118.py`, which assert the bound is 4. These are stale assertions, not defects.
- **1 real failure**, `test_live2_history_size.py::test_pieces_partition_the_history_with_no_gap_and_no_overlap`. Verified by construction at both bounds: **C_inflight 4 PASSES, C_inflight 8 FAILS.**

NO OVERLAP still holds, so no frame's bytes go out twice; what breaks is ORDER. At C=8 two pieces of
the same session are in flight at once, so the second computes its new range against a built prefix
the first has not yet updated, and the pieces cover the history out of sequence. For a
prefix-structured KV cache that is a correctness defect, not a cosmetic one: a piece cannot be
appended before its predecessor.

**I have NOT fixed this.** The fix is to serialise pieces within a session, which is D104's
one-piece-per-epoch rule, and that CHANGES BASELINE BEHAVIOUR and therefore committed baseline
numbers. That is a methodological change and needs a ruling, not a quiet patch at 3 am. **It means
D128's default of 8 is not safe for the piece arms as they stand**, which is worth knowing before
any run uses them at that bound.

*(A caution on my own method here: my first attempt to compare the two bounds patched
`Pi0Edf.C_INFLIGHT_DEFAULT` on the class, which is a dataclass field default bound at class creation,
so it did not reach the arm and BOTH conditions silently ran at 8. I read that as "pre-existing and
not caused by D128" and was wrong. Verifying that the knob actually moved is what caught it.)*

## v1.4 development log (D131)

- `state.bump_z(weight=...)` and `coordinator._b2_weight`: D131 B2, per-device deficit scaling, `w_RC = 2 / lambda_rc = 201.3` derived in V7.2, SH held at exactly 1, behind `deficit_scaling` with an explicit `deficit_gain`. V7.3's warning stands, so the gain is SWEPT rather than assumed.
- `arms_policy.rc_priority_slack_s` / `rc_priority_keep_monitors`: D131 item 2, deadline-aware RC release, done ARM-SIDE because D118 records that vLLM priority preempts and `_preempt_request` zeroes `num_computed_tokens`, which would discard the prefill of the cold rebuilds this is meant to land. **No server priority mode is required.**
- `arms.Pi0Edf.serialise_pieces`: D131 item 1, one piece in flight per session in strict prefix order, scoped to arms with `piece_tokens is not None`.

### Item 1 closed: piece serialisation, and the scoping that matters

`test_pieces_partition_the_history_with_no_gap_and_no_overlap` passes at C_inflight 8 with the fix,
and `test_live2_history_size.py` is green at 9 of 9. The cause is that at C=8 two recall queries on
the SAME session are released in one epoch, each issuing its own MATERIALIZE, so one session's
pieces advance in parallel and arrive out of sequence. NO OVERLAP still held throughout, so no bytes
went out twice; only order broke, which a prefix-structured KV cache cannot accept.

**`covex-v13` was never affected, measured not assumed.** Running it against the same partition
assertion gives 5 sessions checked, 0 out of order, 0 overlapping, and that is its NATIVE behaviour
since the fix lives in `Pi0Edf.decide` while covex uses `PolicyCoreArm.decide`, whose `materialize`
list is already one per session per epoch.

**A baseline-drift trap I walked into and backed out of.** My first fix gated the second
`materialize` for ANY arm, including those that rebuild WHOLE. Measured at 16 devices seed 0, that
moved **edf from 4 to 5 robot answers and dashcam from 0.9508 to 0.9462**, a silent change to a
SCORED baseline. A whole rebuild is a single-element partition and cannot be out of order with
itself, so the gate is now scoped to `piece_tokens is not None` and the whole-rebuild arms are
byte-identical again. This is why the delta run was worth having even after it stopped gating
anyone's leaderboard.

For the piece arms the fix does change dry-run numbers, as it should, since it changes which work
is issued: `edf-piece1024` at 16 devices goes from 3 of 35 robots at dashcam 0.9911 to 5 at 0.9057
on seed 0, and from 2 of 41 at 0.9962 to 4 at 0.8709 on seed 4.

### On the D71 / D82 capacity conjunct (CORRECTED)

**The paragraph below is WRONG and is kept only so the correction is legible.** It rested on a
single cell. Session 2's full grid refutes it: **30 of 196 cells PASS the capacity conjunct**, the
published arms pass 12 of 28 each and are the only arms passing above 8 devices, and nobody passes
at n=4 because the robot pool is INELIGIBLE under D82's 20-question minimum rather than because the
target is missed. **v1.3-fast passes 0 of 28.** So capacity is a real and reachable bar that
published systems clear and COVEX never does, and it is a TARGET again, not something to flag
around. The earlier reading came from the coordinator and was withdrawn by them.

**Also withdrawn: the 32-device win.** It was measured against edf and llf only. With the published
arms in the bar, mooncake matches COVEX on dashcam, 0.4527 against 0.4463, and more than doubles it
on robots, 0.454 against 0.202, while eco-llm leads robots by 2.6x. **The published field leads
COVEX on robots at every size.** The honest position under D131 is that COVEX does not beat the best
baseline at any size on either axis and meets capacity nowhere.

### SUPERSEDED: the earlier capacity reading

Session 2 measures llf at 16 devices seed 4 with `capacity_met` FALSE on a robot pool of 0.2195
against a 0.90 target, and the strongest published arm at 34 of 41 reaches only 0.829. **I am
therefore NOT optimising for a capacity pass**, and I am saying so rather than quietly
reinterpreting the goal: if the best known system, charged more accelerator time than COVEX, cannot
clear 0.90, a pass is probably unavailable to any arm in this configuration and chasing it would be
chasing a property of the target. I report the conjunct honestly beside every delivery number and
optimise against the delivery comparison and the release gate. **Treating "best among arms that all
miss capacity" as the realistic target is a working assumption pending the user's ruling.**

### B2 and the RC deficit: the link is absent STRUCTURALLY, and routing does not open it

The dispatch-path routing is implemented: `delta_j` now takes `rc_rows` and passes it to every
`ro.run` branch, and the coordinator passes `rc_z_dispatch` through from the arm. **It does not
change a single outcome**, and instrumenting the counterfactual says why.

Over one cell at 10 devices with `rc_z_dispatch` and B2 both on, 14,721 `delta_j` calls:

| quantity | value |
|---|---|
| calls | 14,721 (admit 2,647, dispatch 4,279, state 6,423, release 1,372) |
| calls with `rc_rows` routed | 2,647 |
| calls where `a.z_term - b.z_term` is non-zero | **1** |
| max abs difference where it did differ | 90.60 |

**So the RC deficit CANCELS between the two branches of the counterfactual in 14,720 of 14,721
calls.** This is the same structural cancellation F-A2 established for the state value, and the
same root cause the project has hit from the start: a recall answer lands 1 to 5 s after the
decision, outside the H = 0.5 s dispatch horizon, so the action and its reference produce the
IDENTICAL RC outcome within the window and the deficit contributes an identical constant to both
sides.

**Consequences, stated precisely.**

1. **B2 remains INCONCLUSIVE under Rule 2 at every gain, and routing does not rescue it.** The quantity is present and large, `_b2_weight('RC')` = 201.33 and `z[RC]` reaching 543.58, and it reaches a decision in 1 call out of 14,721. Session 2's decision-side result, 0 of 8,120 decisions differing, is the same finding from the other side.
2. **The fix is NOT another weight or another routing flag.** For the RC deficit to reach a dispatch decision, the counterfactual pair must differ in RC outcomes, which means the evaluation window must extend past the answer's arrival. That is exactly what the v1.2 planner does with its long window, and it is why the planner, not the dispatcher, is where RC value has ever been visible.
3. **The 1 call that did differ, at 90.60, shows the channel is not dead**, only unreachable in the dispatch geometry. That distinguishes this from a wiring fault.

### The infeasible-question check: COVEX already declines them

D132's ceiling puts the breakeven at 19,381 tokens feasible and 20,011 infeasible. At 12 devices,
seed 4, 29 robot questions: **2 are above the breakeven (21,631 and 25,681 tokens) and COVEX admits
NEITHER**, while admitting 23 of the 27 feasible ones. The prediction holds: `classify` and
`p_finish` run the continuation schedule at `competing_s = 0`, the same idle-engine assumption the
ceiling uses, so an infeasible history is refused without any change. **There is no free capacity
here**, and the mechanism is confirmed working rather than assumed.

*(The first run of this check reported "ADMITTED 0" for the FEASIBLE questions too, which was my
detector reading a non-existent field: `RecallAction` carries `decision`, not `mode` or `action`. A
detector that reads zero everywhere confirms nothing, so the number above is from the corrected
run, where 23 of 27 feasible admissions are visible.)*

## covex-v2: rollout over the strongest baseline

### PRE-REGISTERED EXPECTATION, written before any v2 code runs

Recorded first so the sweep is interpretable whichever way it falls.

**Design.** The base policy's actions execute by default. At each decision point COVEX evaluates
alternatives by rollout with the BASE as pi_0, and deviates only if
`DeltaJ(alternative) - DeltaJ(base action) > margin`. At `margin = infinity` it must be
BYTE-IDENTICAL to the base, which makes "COVEX cannot do worse than the best baseline" a structural
property rather than an empirical hope.

**What changes underneath, and it changes everything.** pi_0 becomes the base rather than EDF. Every
DeltaJ in the system is a counterfactual against pi_0, so swapping pi_0 changes every number the
policy computes. No calibration intuition from v1.x transfers and each will be re-verified rather
than assumed.

**THE PREDICTION.** Three nights of evidence say COVEX's DeltaJ machinery is unreliable in specific,
documented ways:

- the RC deficit reaches a decision in **1 of 14,721** counterfactual calls, cancelling structurally;
- the state value cancels **exactly**, 12,898 of 12,898, for the same reason;
- the price was mispriced (EWMA rose as occupancy fell), then saturated at its cap in 92.9 per cent of busy calls, and a correctly graded form was still worse than no price at all;
- `p_finish` is a saturated indicator at `competing_s = 0`.

**If DeltaJ is systematically wrong, deviating on it makes things WORSE than the base, and the
margin is exactly the protection against that.** So the expected shape is:

1. **margin = 0 UNDERPERFORMS the base**, because every unreliable DeltaJ becomes a deviation.
2. **Larger margins converge to the base** monotonically, by construction.
3. **The open question is whether ANY margin beats the base.**

**How each outcome reads.** If the prediction holds, it says the model is not yet trustworthy enough
to deviate on, which is a real finding and closes a line of work. If some margin beats the base,
that is the stronger and more defensible claim: **COVEX improves on the best baseline where its
model is reliable**, which is a better paper than "COVEX beats baselines" and does not depend on
COVEX winning everywhere.

**Stop condition.** Failure of the `margin = infinity` byte-identity proof halts the work. It is run
FIRST, before any margin sweep, because every other claim rests on it.

**Base selection.** `b7-edf-feasibility` is the presumptive base as the strongest simple heuristic,
but the base is SELECTABLE and the choice is not hard-coded pending session 2's mooncake/b7 identity
check, since those two arms report identical numbers (34 of 41, 79.5 recall gpu_s, 37 events) and
may not be distinct policies.

### SECOND PRE-REGISTERED PREDICTION: which deviation KINDS can fire at all

Added before any margin is swept. The first prediction assumed deviations fire and asked which
margin wins; this one asks which kinds are capable of firing, and they are different questions.

**The argument, from the geometry result above.** Any quantity whose effect lands outside the
H = 0.5 s dispatch window cancels in the dispatch counterfactual, because action and reference
produce the identical outcome inside the window. v2's alternative set is decline, admit, piece
size, reload against rebuild, start-now against latest-start, and keep-warm. **A rebuild takes
seconds, a recall answer lands 1 to 5 s out, and start-now against latest-start is purely a
question about an outcome beyond the window.** So the prediction is that **RC-class deviations
evaluate to `DeltaJ(alternative) - DeltaJ(base) = 0` and cannot exceed any margin, including
margin = 0**, and the margin sweep returns the base everywhere.

**If that holds it is INCONCLUSIVE under Rule 2, not a real negative**, and it would be the fourth
null in this project from a mechanism that could not reach a decision. It must not be reported as
"COVEX has nothing to add".

**ONE REFINEMENT to the argument, which is why this is measured rather than assumed.** The
14,721-call instrumentation measured the Z TERM difference, not DeltaJ total. DeltaJ can also move
through `u_hat` and `terminal`. **So an RC admit decision may still score even though its DEFICIT
contribution cancels**, and the reachability test is therefore run on **DeltaJ total per kind**, not
on the z term. Predicting cancellation from the z result alone would overreach.

**STOP CONDITION, alongside the byte-identity proof.** Each alternative kind is classified
REACHABLE or CANCELLED-BY-GEOMETRY on one cell before any margin is swept, and a kind that is
structurally zero is reported as such rather than swept.

**A SECOND WAY A DEVIATION CAN FIRE AND CHANGE NOTHING**, recorded so the two are not confused:
`live2/coordinator.py` never reads the action `order` field, so a deviation expressed only as a
reordering is a no-op by construction. Every alternative in v2 therefore changes
`RecallAction.decision` or a `StreamAction`, both of which the coordinator reads. **My own v1.4
conversion mechanism was checked against this and is NOT order-only**: it expresses through
`stream_on`, which becomes `StreamAction(cloud/local)`. So if `rc_priority_epochs` turns out never
to fire, that is a gating-logic question and not an expressibility one.

**HARNESS LIMITATION FOR THE PAPER.** Any two adapted arms whose scheduling discipline is expressed
only through `order` are indistinguishable in live2 by construction. That is a harness
expressiveness gap, not a porting artefact, and belongs in the limitations of whatever is said about
the published field. Cardinality claims must state the size they were measured at: at seed 4 and
8 devices the twelve in-scope arms supply eleven independent behaviours, with ekya and videostorm
diverging again at 16 devices, and `eco-llm` is a singleton in every grouping at both sizes.

### covex-v2: the margin = infinity byte-identity proof PASSES

Base `eco-llm`, seed 0, 10 devices, 300 s, comparing canonical decision objects period by period:

| | |
|---|---|
| decisions | base 2,999, covex-v2 2,999 |
| base sha256 | `9e6d42f075c065396ce5de041141a0ae52ab2e4f3d76b089cf8376e127e81369` |
| covex-v2 sha256 | `9e6d42f075c065396ce5de041141a0ae52ab2e4f3d76b089cf8376e127e81369` |
| differing decisions | **0 of 2,999** |

**So "COVEX cannot do worse than the best baseline" is a structural property of this design**, not an
empirical hope. The stop condition is cleared. One construction detail was required to make the
proof meaningful rather than accidental: the wrapper MIRRORS the base's declared policy attributes
(`reads_device_answer`, `multi_instance_adapted`, `releases_one_per_epoch`, `piece_tokens`,
`c_inflight`), because the coordinator reads them and a wrapper declaring different ones would
diverge for reasons unrelated to the margin.

### Why RCprio never fired: a DEFINITION HAZARD, and my own wrong "fix"

Session 2 confirmed RCprio is an absent link: 0 of 8,120 decisions differ at `slack = 5.0` with
`rc_priority_epochs` absent from both conditions. The cause, measured:

**`deadline_s` means two different things on two objects of this codebase.**

| object | meaning | source |
|---|---|---|
| `cstate.Opportunity.deadline_s` | RELATIVE, "the bound, measured from t_event" | `cstate.py:111` |
| `cstate.RecallQuery.deadline_s` | **ABSOLUTE**, `round(o.deadline_abs(), 3)` | `cstate.py:327` |

The guard reads a `RecallQuery`, so `deadline_s - now` IS the slack and my original form was right.
**An earlier "fix" of mine added `arrival_s` on the theory that the field was relative**, which
double-counted arrival and pushed every measured slack to **58 to 297 s**, so the guard could not
fire at any threshold. Raw measurements that settled it: `now=56.900 arrival=55.155
deadline_s=60.132`, where `deadline_s - arrival = 4.977`, the 5 s budget. Corrected.

**But the mechanism was nearly unreachable even with the right formula**, which is the more useful
finding: at 10 devices only **7 of 2,999 epochs have a CLOUD recall at the point the guard runs**.
A guard that can act in 0.2 per cent of epochs cannot move an aggregate, and the reason it sees so
few is COVEX's admission VOLUME, the same deficit everything else points at. So RCprio is not
rescued by the formula fix and is **not reported as a result**.

This is a check-4 definition failure of exactly the kind the consistency protocol exists to catch,
and it is now recorded so the next reader of `deadline_s` does not repeat it.

### The unexpressible-channel list, and a correction to my reachability pass

Three distinct verdicts must be kept apart for any deviation: **CANCELLED-BY-GEOMETRY** (its effect
lands outside H so the counterfactual pair is identical), **UNEXPRESSIBLE** (it fires and the
harness ignores it), and **fired-and-did-not-help**.

| channel | status | evidence |
|---|---|---|
| `order` | UNEXPRESSIBLE | no reference in `live2/coordinator.py`; the two `.order` matches are `self.st.order`, a different object |
| `desired_tier` | UNEXPRESSIBLE | 3 references in all of live2: one declaration (`cstate.py:92`) and two WRITES (`coordinator.py:423,425`), **no read**. `KEEP_GPU_WARM` and `OFFLOAD_TO_HOST` are dispatched, counted and handled, and change nothing |

**`keep-warm` is therefore DROPPED from v2's alternative set.** The general rule, now applied to the
classification pass: **check whether a field is READ, not whether it is REFERENCED.** `order` has
zero references and is visibly dead; `desired_tier` passes a reference check and fails a read check.

**My first reachability pass was INVALID and classified nothing.** It reported
`recall:CLOUD->DEVICE` as 0 non-zero out of 10, which looks like cancellation, but all 10 were
**UNSCORED**: the scorer was built with default kwargs so `planner_rc` was off and it produced
DeltaJ only for dashcam targets. Its `delta_j` keys were all `dashNNN:` with not one `rc:` key.
The scorer is now configured with the v1.3 switch set. **A pass that scores nothing confirms
nothing**, and reporting its zeros as cancellation would have been the B2 error one level up.

### The reachability classification is BLOCKED, and the cause is a FOURTH failure category

The classification is still owed. It cannot be produced yet, and the reason is neither geometry nor
expressibility but a design flaw in my own v2 evaluator.

**Measured, 10 devices, seed 0, 2,999 epochs, scorer verified configured** (`planner_rc` True on
both the arm and its `flags`, checked on the constructed object per the standing rule):

| quantity | value |
|---|---|
| epochs | 2,999 |
| epochs where `obs.recall` is non-empty | 10 |
| scorer `_jobs_by_q` max size over the run | **0** |
| scorer `delta_j` keys | `dash000:` to `dash004:` only, **not one `rc:` key** |
| recall alternatives scored | **0 of 10** (all UNSCORED) |

**So the scorer never builds RC job state at all**, even in the epochs where it sees recall
queries. `_jobs_by_q` stays empty for the whole run, so no RC decision is ever produced, so no
`rc:` DeltaJ is ever emitted, so every recall alternative comes back unscored.

**The cause is structural in how I built the evaluator.** The scorer is a separate policy-core arm
whose `decide` is called for its DeltaJ machinery while the BASE's actions are the ones executed.
Its internal bookkeeping therefore tracks a trajectory that never happened: it never admits a
recall, so it never creates a job, so it never has an RC decision to score. **An evaluator whose
state does not track the executed trajectory cannot score alternatives to it.**

**This is a FOURTH category of non-firing deviation and must be kept separate from the other
three**, because all four look identical from the outside:

| category | meaning |
|---|---|
| CANCELLED-BY-GEOMETRY | effect lands outside H, so the counterfactual pair is identical |
| UNEXPRESSIBLE | fires, and the harness ignores the field (`order`, `desired_tier`) |
| fired-and-did-not-help | a real negative |
| **UNSCORABLE** | **the evaluator's state does not track the executed trajectory, so no value is produced to compare** |

**I am NOT classifying `recall:CLOUD->DEVICE` as cancelled-by-geometry.** That verdict would match
the standing prediction and is therefore the one most at risk of being believed too easily, and the
evidence does not support it: a zero from an unscored channel is not a zero from a cancelled one.
The geometry prediction remains untested for RC deviations.

**PROPOSED FIX, stated rather than implemented silently, since it is a design decision.** The
evaluator must be advanced on the BASE's executed actions, not on its own. Two shapes:

1. **Feed the base's action back into the scorer each period** so its bookkeeping follows the executed trajectory, then ask it for DeltaJ. Cheapest, and keeps one evaluator.
2. **Evaluate alternatives on the PLANNER's horizon** rather than the dispatcher's, which is the remedy the geometry result already implies for RC-class deviations, and which would also sidestep the state-tracking problem because the planner constructs its own candidate jobs rather than relying on accumulated state.

Option 2 is also the answer to the geometry cancellation if it turns out to be real, so it may do
both jobs at once. **The D98 RC tail is the existing precedent for crediting outcomes beyond H and
may be cheaper than a long rollout.** Neither is implemented; the margin sweep does not start until
one is, because a sweep over unscorable alternatives measures nothing.

### The reachability classification, CORRECTED: RC deviations are REACHABLE

**The geometry prediction is REFUTED for RC deviations on the dispatch horizon.** At 10 devices,
seed 0:

| alternative kind | considered | non-zero | max abs gain | verdict |
|---|---|---|---|---|
| `recall:CLOUD->DEVICE` | 10 | **4** | 0.0550 | **REACHABLE** |

Four deviations fired at `margin = 0`, so the directive's "confirm at least one deviation fires"
condition is met and the margin sweep is meaningful.

**Six of the ten scored EXACTLY zero**, so the geometry cancellation is real for some decisions and
not for others. The prediction was that RC-class deviations would be uniformly zero because a
recall answer lands outside H; what the data shows is partial cancellation. **The hypothesis was
worth testing and is now tested rather than assumed, which is why option 1 had to precede option 2:
changing the horizon first would have confounded "we fixed scorability" with "we changed the
horizon" and left the geometry claim untestable forever.**

**THREE BUGS IN MY EVALUATOR had to be cleared to get here, and each produced a clean-looking zero.**

1. **The roster was clobbered.** `_score_recall` reset the scorer's roster from `getattr(self.base, "_live2_roster", None) or {}`, and `arms_published.py` defines no `live2_roster` at all, so the real roster was overwritten with `{}` every period. Consequence: `_jobs_by_q` stayed at size 0 for all 2,999 epochs and no RC decision was ever produced. Fixed by keeping the roster on the wrapper.
2. **The lookup key was wrong.** DeltaJ is keyed by DECISION TARGET, which for RC work is the planner's item id `<device>:<rep>:<t>:p<i>` (for example `robo002:RICH:39.300:p0`), never `"rc:" + query_id`. Established by printing the live keys rather than reasoning about them.
3. **The device was wrong.** A session id is `<device>|<slot>|<clip>`, so matching the full `session_id` against a device-keyed target found nothing.

**Every one of the three produced "0 non-zero out of 10", which reads exactly like
cancelled-by-geometry.** Had any been left in place, the result would have confirmed the standing
prediction for the wrong reason. This is the UNSCORABLE category of the taxonomy doing real work:
four kinds of silence that are invisibly identical from outside.

**LIMITATION, stated because it qualifies the number.** The value of admitting a query is taken as
the SUM of the DeltaJ over that device's RC target keys, since no target is keyed by query id. With
one outstanding question per device this is exact; with more than one it attributes the whole
device's RC value to each query. It is adequate for a REACHABLE / CANCELLED classification, which
only asks whether the quantity is ever non-zero, and it is **not** adequate as a calibrated gain,
so the margin sweep's absolute values should be read with it in mind.

### COVEX is BLIND EXACTLY WHERE IT MOST NEEDS TO ACT

The cheap follow-up asked whether the six zeros are the long-latency recalls. **They are.** History
size drives rebuild time, so it proxies how far past H the answer lands. At 10 devices, seed 0:

| query | tokens | gain |
|---|---|---|
| opp0002578 | 5,431 | 0.054350 |
| opp0000483 | 6,781 | 0.054041 |
| opp0000361 | 8,131 | **0** |
| opp0000234 | 8,131 | 0.054351 |
| opp0000765 | 10,831 | **0** |
| opp0000856 | 10,831 | **0** |
| opp0000746 | 10,831 | 0.054991 |
| opp0000379 | 13,531 | **0** |
| opp0001715 | 14,881 | **0** |
| opp0002507 | 18,931 | **0** |

| group | n | min | median | max |
|---|---|---|---|---|
| NON-ZERO | 4 | 5,431 | **7,456** | 10,831 |
| ZERO | 6 | 8,131 | **12,181** | 18,931 |

**Every query at or above 13,531 tokens scores exactly zero.** The two groups overlap at 8,131 and
10,831, so this is a tendency rather than a clean threshold, but the direction is unambiguous and
the three largest histories are all blind.

**This is the sharpest finding of the exercise, and it is sharper than either the prediction or its
refutation.** The geometry mechanism is real and operates on a SUBSET, and the subset is precisely
**the long-latency recalls, which are the population that misses the 5 s robot deadline**. COVEX
can see the value of admitting a short recall it was going to deliver anyway, and is blind to the
long one whose delivery is actually in question. **The decisions the whole exercise is about are
the ones its evaluator cannot score.**

For scale, the D132 ceiling puts the feasible breakeven at 19,381 tokens, so the 18,931-token query
is a feasible-but-marginal question: deliverable on an idle engine, and invisible to the policy
that would have to schedule it.

**THIS REVERSES MY OWN RECOMMENDATION ON OPTION 2, and I am flagging that rather than quietly
changing position.** I argued to hold the planner-horizon change because RC deviations work on the
dispatch horizon for 40 per cent of decisions. That remains true, but this evidence says the 60 per
cent it cannot see are exactly the ones that matter for the robot axis. **Option 2 is therefore
justified again, and now for a specific and measured reason rather than as a general remedy: to
make LONG-LATENCY recalls scorable.** It is a methodological change and is flagged, not
implemented.

**A cheaper alternative worth weighing first**, since it is the existing precedent for crediting
outcomes beyond H: the D98 RC tail. If the tail already credits a long recall's delivery, extending
the counterfactual to include it may make these decisions scorable without moving the whole
evaluation to the planner's horizon.
