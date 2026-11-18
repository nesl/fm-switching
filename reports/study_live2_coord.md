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

## H9. Addendum: answers bypass the decision loop, and a real run refuses a frame it cannot send

Two changes on top of H1 to H8, both user-directed after H5 showed `policy-core` at 64 devices
missing the lateness rule at p99 110.3 ms.

### H9.1 The scheduler is off the answer's return path

In deployment the scheduler does not sit between the engine and the device. The completion path
is now split in two:

* **on the I/O thread, the instant the request finishes** (`coordinator._on_complete`): derive
  the timings, run the committed score extraction, build the `cloud_answer`, and hand it to the
  transport. It touches NO mutable policy state. The opportunity is read for its `kind` and
  `deadline_abs()` only, both fixed when the trace created it.
* **at the next decision epoch** (`coordinator._apply_completion`, called from `_collect` exactly
  where it was called before): apply the state changes, write the request log, tell the arm
  through `live2_completed`, and settle the opportunity.

So what the policy sees mid-decision is unchanged and it learns of completions at the next epoch,
as before. In the split configuration the forwarding is done by a child-side writer thread fed
from a queue (`coordinator.on_answer`), because appending the answer to a list was not enough:
the bridge's drain still ran on the child's main loop, which is exactly the thread a long
decision blocks. `EmulatorBridge(forward_answers=False)` then stops the loop re-sending them.

**Two fixes were needed, and the second was the one that mattered.** Forwarding from the I/O
thread alone moved `policy-core` at 64 devices from p99 110.3 ms only to 93.2 ms, with all 966
answers confirmed forwarded by the I/O thread. The reason is a stamping error the prompt's own
wording pointed at ("stamped with its true completion time"): a request was stamped
`sent_s = t`, the nominal instant of the epoch that decided it, while it actually went on the
wire up to 130 ms later, after the decision finished. Every completion derived from it was
therefore understated by exactly that delay, so a promptly forwarded answer still carried a
`t_done` behind the fleet's clock. Requests now carry their TRUE submission time,
`t + (perf_counter() - epoch_start)`, and the delay is logged per request. A dry run has no wall
clock and keeps the nominal instant, which is what keeps its logs deterministic.

| `policy-core`, 64 devices, mode A | lateness p99 | lateness max | valid | decision p99 | submit delay p99 |
|---|---|---|---|---|---|
| H5, before the addendum | 110.256 ms | 488.336 ms | no | 115.694 ms | not logged |
| answers forwarded from the I/O thread | 93.219 ms | 416.980 ms | no | 103.964 ms | 114.404 ms |
| + the true submission stamp | **8.196 ms** | 303.711 ms | **yes** | 112.868 ms | 118.979 ms |

**The policy's decision cost is now paid where it belongs.** It no longer shows up as lateness;
it shows up as submit delay (p50 38.0, p90 84.5, p99 119.0, max 131.8 ms over 973 requests),
which is the honest consequence of a 100 ms-period scheduler that takes p99 113 ms to decide: the
request goes out late, the answer is then on time relative to when it was actually sent. Decision
latency and submit delay are both reported per run, separately, so StudyLIVE2-perf has the
quantity it needs to improve.

The residual tail is real and reported rather than smoothed: 138 of 2,301 actions are still over
10 ms and the worst is 303.7 ms, all of them answers. p99 is the acceptance rule and it is met by
a factor of 6; the max is not claimed to be fixed.

### H9.2 A real-server run refuses to start with a frame it cannot send

`live2/preflight.py`. The coordinator resolves `frames_root / frame_ref` and, when the file is
absent, sends the frame as a uuid-only REFERENCE, which is the committed StudyRH7 wire form for
"you have already seen these bytes". For a frame whose bytes were never uploaded that is a false
claim about the engine's cache. On flash it only shrinks the body; against a real engine it
corrupts the prefix the study measures.

`require_frames(trace_dir, frames_root, server_kind)` is called by `run_live2_real.py` before
anything is built, writes `frames_preflight.json` into the run directory, puts the report in the
header, and raises `MissingFrames` so no partial run directory is produced. An absent file and a
present-but-empty file are both refused. Fake and stub runs are exempt by `server_kind`, because
the fake-server tests build deliberately partial stores, and the exemption cannot be taken by
accident on a real run.

The finding that motivated it is pinned as a test rather than left in prose: a seed-0, 8-device,
120 s, mode-A trace asks for 1,278 frame references and **30 of them have no row in the committed
Part-1 manifests**, every one an S-EMBER D2 reference (the manifests reach each session's last
question; the trace keeps appending history to the session's end). The test asserts the exact
pair (30, 1278) and that all 30 are D2 references, so when the H100 extends the D2 store to each
session's end the test fails loudly and says that the gate can be relaxed and this issue closed.

### H9.3 Acceptance re-run: 8 of 8

| arm | devices | mode | p50 | p90 | **p99** | max | within 50 ms | decision p99 | submit delay p99 | requests |
|---|---|---|---|---|---|---|---|---|---|---|
| `edf` | 8 | A | 0.151 | 0.222 | **0.263** | 0.368 | yes | 0.241 | 0.645 | 711 |\n| `edf` | 8 | B | 0.082 | 0.209 | **0.259** | 0.318 | yes | 0.255 | 1.877 | 349 |\n| `policy-core` | 8 | A | 0.151 | 0.236 | **0.277** | 0.369 | yes | 4.244 | 6.754 | 767 |\n| `policy-core` | 8 | B | 0.139 | 0.211 | **0.260** | 0.337 | yes | 8.203 | n/a | 0 |\n| `edf` | 64 | A | 0.068 | 0.204 | **0.260** | 1.318 | yes | 0.789 | 2.023 | 597 |\n| `edf` | 64 | B | 0.066 | 0.203 | **0.262** | 3.556 | yes | 0.684 | 100.147 | 34 |\n| `policy-core` | 64 | B | 0.062 | 0.164 | **0.925** | 108.089 | yes | 90.271 | 44.872 | 4 |\n| `policy-core` | 64 | A | 0.081 | 0.179 | **22.174** | 349.390 | yes | 101.914 | 114.011 | 962 |

All milliseconds, `all_within_limit` true, fairness digests identical across arms at every size
and mode. The grid's `policy-core` 64 / A cell reads p99 22.174 ms where the single re-run above
read 8.196 ms: the tail varies run to run because it is driven by where a long decision happens
to fall against the arrival pattern. Both are inside the limit by a wide margin, and the figure
reported as the acceptance result is the grid's.

Decision latency and submit delay now separate cleanly by arm, which is the quantity
StudyLIVE2-perf is aimed at: `edf` decides in p99 0.24 to 0.79 ms at every size, while
`policy-core` goes from p99 4.24 ms at 8 devices to 101.91 ms at 64. The 100.1 ms submit delay in
the `edf` 64 / B cell is not a decision cost: that cell issues 34 requests, so a single
pull-mode request waiting on its frame dominates the percentile.
