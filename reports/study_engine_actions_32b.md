# StudyV5-ENGINE, the 32B confirmation leg: pre-registered protocol

Flash session, 2026-11-20. Artefacts:
`experiments/orchestration/live2/confirm_engine_actions_32b.py` (the script the H100 runs),
`results/orchestration/live2/v5/engine_actions_32b_confirmation.json` (its one output, written on
the H100).

Source row: `research/EXPERIMENTS.md` **StudyV5-ENGINE**, user-authorized 2026-11-20, which names
this leg explicitly: "h100nvl (all three real measurements, on the deployment stack, vLLM 0.31.0
with native offload 27 GiB, during ONE short confirmation break at a run boundary)". Source
module: `experiments/orchestration/live2/engine_actions.py` and
`reports/study_engine_actions.md` section 1 (its interface note). Source decisions: D84, D148,
D150, D151, and `research/policy_spec_v5.md` section 8.

**REGISTER, first.** This report is a **PRE-REGISTRATION**. It contains no measurement. Steps 1,
2a (the instrumentation side), 4 and 5 of CLAUDE.md's mechanism verification are written here
before the run, as the protocol requires; Step 2's value column, Step 2b's decision diff and Step
3's traced unit are produced BY the run and land in the result JSON, because they are properties
of the live engine and cannot be known on flash. The only numbers below that are measured are the
**flash dry-validation** counts in section 8, and those are counts of the script's own logic
against a CPU stub, never evidence about an engine.

**STACK RULING, unchanged and restated so no reader hopes otherwise.** Flash cannot run any of
these three measurements. vLLM here is 0.8.5, which does not support Qwen3-VL and has no native
host KV tier, so reload-from-host is not measurable on this box at all; the disk is at 99 percent
and nothing is to be installed. Flash validates the script's logic and the H100 produces the
numbers that count.

---

## 1. What the H100 runs, and what must be running

```
~/.venvs/fm-switching-vllm/bin/python \
    experiments/orchestration/live2/confirm_engine_actions_32b.py
```

No flags are needed. The defaults are the committed round-1 server:
`--base-url http://127.0.0.1:8031`, `--served-model 32BI`.

**Server requirement: the live2 ROUND-1 32B server, already running, and nothing else on the
GPU.** Qwen3-VL-32B-Instruct @0cfaf481 served as `32BI` on `127.0.0.1:8031`, vLLM 0.31.0, the flag
list in `results/orchestration/live2/pre/live2_pre_server.json`:
`--enable-prefix-caching --enable-prompt-tokens-details --mm-processor-cache-gb 128
--kv-offloading-backend native --kv-offloading-size 27 --max-model-len 32768
--limit-mm-per-prompt '{"image": 640, "video": 1}'`, GPU KV pool 62,944 tokens.

The script **starts nothing, installs nothing, compiles nothing and edits nothing.** It makes HTTP
requests to that server, reads `/v1/models` and `/metrics`, and writes one JSON. If the server is
not there, or serves another model, it stops with the reason and the fix in one line. The operator
sets STOP, runs this, and resumes.

**Operator notes.** (a) The run issues about 130 requests and uploads about 110 MB of base64 over
localhost; with `--enable-log-requests` the server log will grow accordingly. (b) `--dry` must
NEVER be passed on the H100: it substitutes placeholder frames and a fixture frontier. (c) Nothing
else may use the server during the run: the TTFT numbers are taken at concurrency one and a
co-tenant invalidates them.

**Expected wall clock: 6 to 10 minutes.** Composition, from the committed cost curves: preflight
about 10 s; M1 three repetitions at about 12 s; the frontier ladder about 70 s (268,584 text
tokens at the ENG1c-consistent 4 to 6k tok/s); M3 three repetitions at about 26 s; M2 six
condition-repetitions at about 35 s. `--duration-budget-s` defaults to 900 s and is checked before
every phase and every repetition; a phase that does not fit is recorded `NOT ATTEMPTED (budget)`
rather than overrunning the break. Lowering it is safe: the phases run in the order preflight, M1,
frontier, M3, M2, so a short budget costs M2 repetitions and not M3.

---

## 2. The three measurements and their committed instruments

| | claim | the engine quantity that answers it | comparator |
|---|---|---|---|
| **M1** | a warm-ahead prefill raises cached tokens at question time | `prompt_tokens_details.cached_tokens` on the question request | the same question over the same frames on a different device, no warm-ahead |
| **M2** | a touched history survives where an untouched one is evicted | `cached_tokens` on a full-prefix probe of each history after pressure | the same pressure with NOTHING touched, which predicts the opposite winner |
| **M3** | reload-from-host beats a cold rebuild | wall-clock TTFT and total of a host-resident reload | COLD_KV (same uuids, new salt) and COLD_FULL (fresh device, bytes on the wire) |

**Everything the script sends is a committed body.** `bodies.build_body` builds every request:
the build pieces are the coordinator's own build body (`coordinator.py:752`, header `D2 history`,
`max_tokens=1`, kind `piece`/`whole`), and the question is the committed StudyR1 recall body
(StudyO's own question wrapper, cell K1's generation parameters). The question itself is read out
of the committed EVAL split (`fleet/data_sources.eval_sessions()`), so no question text is
invented: the candidates are one per EVAL session, each session's LAST question, in sorted-session
order, and the script takes the first whose frames actually resolve on the host. The last question
is used because it has the most history behind it: 124 frames at the committed 2 s D2 stride need
248 s of session, which 138 of the 164 EVAL sessions clear at their last question against 5 at
their first. The frames are the round-1 stored D2 JPEGs of that session, 124 of them, which at the
committed 90 tok/img plus the 31-token header is 11,191 tokens, against the committed D56 nominal
history of 11,184. All three frame-resolution routes (part-2 manifest, `encode_log.jsonl`, and the
`encode_jpeg.py` name convention) are implemented and were exercised on flash against a
constructed store; a session whose frames are missing costs a candidate, not the run.

**Cache keys are the committed ones.** `cachekeys.cache_salt` per device and
`cachekeys.mm_uuid(run_tag, device, session, frame_ref)` per frame, per D84. A frame whose bytes
the engine has seen is sent as `{"type": "image_url", "image_url": null, "uuid": ...}`, the
committed StudyRH7 wire form, and that is the mechanism M1 depends on. The run tag carries the
wall clock, so **no run of this script can be served from another run's cache entries.**

**This is also what makes the cold arms fair rather than merely cold.** Two arms over the *same
JPEG files* on *different device ids* get different salts and different mm uuids, so they are
cache-isolated by construction while carrying identical token counts. `cachekeys.check_isolation`
is run over the run's own recorded bodies and its verdict is in the JSON, with its one deliberate
exclusion named (section 5, COLD_KV).

---

## 3. Step 0: what would make each measurement uninterpretable

Asked and answered before the run, which is the whole point of the step. Each is a live check in
the script, not a hope.

**Everything, at once: `cached_tokens` not being reported, or prefix caching not serving
repeats.** Then every number in the run is a zero that means nothing. **Check:** a prefix-cache
POSITIVE CONTROL in the preflight, before any measurement. A ~600-token text body is sent, then
repeated under the same salt, then repeated under a fresh salt. The same-salt repeat MUST report
reuse above one vLLM block and the fresh-salt repeat MUST NOT. A failure in **either** direction
stops the run and marks all three NOT ESTABLISHED: a control that cannot fail is not a control,
and an impossible success is as diagnostic as an impossible failure (CLAUDE.md consistency check
7). The control's raw usage keys are dumped into the JSON.

**M1, specifically: the "cold" arm not being cold.** If D84's salt did not isolate the prefix
chain, the no-warm-ahead arm would be served from the warm arm's cache and the comparison would
read as a null. **Check:** the fresh-salt leg of the positive control is exactly this test, and
the per-rep gate requires the cold arm at or below one block (16 tokens), StudyENG1c's own cold
gate (`study_eng1c_hostfull.py:362`).

**M1: a TTFT gap read as prefill alone.** The warm arm's question uploads no image bytes and the
cold arm's uploads all of them, because a uuid the engine has never seen cannot be resolved. The
gap therefore contains avoided upload and avoided vision encode as well as avoided prefill.
**Check:** the asymmetry is declared in the result JSON under `M1.design.declared_asymmetry`, the
headline claim is about cached tokens and not about TTFT, and request bytes are recorded per row.

**M2: the pressure missing the one-history window.** M2 needs traffic that evicts exactly one of
two histories. Size it too small and both survive; too large and both go. Either way the touch is
invisible and the result reads as a null. The committed pool sizes do not settle it: it is not
known a priori whether the observable reuse window is the SUM of the 62,944-token GPU pool and the
110,592-token host tier (store-on-eviction) or just the host window (write-through), a 1.57x
difference. **Check:** the frontier is **MEASURED on the live server** before M2 runs, by a ladder
of 24 one-history text sentinels probed youngest-first and stopped at the first miss, so reading
the ladder does not disturb it. M2's pressure is then `(frontier - 1)` histories. A repetition in
which both histories hit or both miss is recorded `INDETERMINATE` and is evidence about the
sizing, never about the touch. The measured frontier is also reported against both hypotheses,
which settles the write-through question as a side effect.

**M2: something other than the touch deciding the winner.** **Check:** the NOTOUCH control, which
takes the identical pressure and predicts the OPPOSITE winner (section 6).

**M2: being read as confirmation of the policy's touch LEVER.** It is not, and this is the single
most likely misreading of this report. `coordinator._enact` handles `KEEP_GPU_WARM` by setting
`SessionRec.desired_tier` (`coordinator.py:482`) and **emits no request**, so a harness touch
cannot move the engine's LRU at all. M2 confirms the ENGINE PROPERTY the lever depends on.
**Check:** the caveat is written into the result JSON at `caveats.touch_wiring` so it travels with
every citation.

**M3: timing something that was not on the host tier.** This is the false pass the brief warns
about, and it would ship a mechanism whose trigger state has never been observed. **Check:** two
independent gates, both required. A TWIN history, built from the same frames on its own device
salt and taking the same pressure, is probed FIRST and classified by StudyENG1c's committed
residency rule over the server's own `prompt_tokens_by_source` / `external_prefix_cache_*`
counters; and the timed reload's OWN counter delta is classified too. Both must say `host` or
`partial_host`. A repetition that fails is DISCARDED and counted. Zero verified repetitions means
M3 is **NOT ESTABLISHED**, and no timing is called a reload. If the server exposes neither counter
family, M3 is NOT ESTABLISHED before a single request is sent.

**M3: verifying on the object you then time.** A probe reloads what it probes, so residency cannot
be verified on the subject. Hence the twin. The twin costs one extra build and one extra probe per
repetition and is the reason M3 can say "verified before timing" at all.

**The comparator about to change, a default about to be restored, a dependency keyed into the
analysis.** None apply: this leg depends on no other run's output, compares no policy arms, and
reads no committed default that another session is editing. The files another session is editing
right now (`bodies.py`, `coordinator.py`, `fleet/trace.py`, `run_live2_real.py`, `scorer/score.py`,
`frozen_headline.py`, `fleet/data_sources.py`) are **read, not written**, by this script, and the
two it imports (`bodies.py`, `data_sources.py`) are imported as committed interfaces. If either
interface changes, the script fails loudly at import rather than silently sending a different
body.

---

## 4. Step 1: the causal chain, per measurement

**M1.** If a prefill-only request for a session's uploaded frames is issued ahead of any question
(`engine_actions.plan_warm_ahead`, lever 1), then the engine computes and retains the KV of that
prefix, because the request is a normal prefill and prefix caching is on. If the question that
follows offers the same prefix (the committed StudyRH7 uuid-only wire form, so byte-identical
content under the same salt and the same mm uuids, `cachekeys`/D84), then the engine's block
hashes match and the prefill is served from cache, which the engine reports as
`prompt_tokens_details.cached_tokens` and which `backend.cached_tokens_of` reads. The chain's last
link is the one `reports/study_engine_actions.md` 17.6 already records on this build (appended
requests carrying 3,056 to 6,768 cached tokens) and that D150 directs into the belief; this
measurement is that link under a warm-ahead rather than under an append.

**M2.** If a history's prefix is re-read by a request, then its blocks are touched, and vLLM's
free-block queue is LRU, so those blocks move to the young end of the eviction order. If other
traffic then allocates more blocks than the reuse window holds, the engine evicts from the old
end, so the history that was NOT re-read crosses the frontier first and the one that was re-read
does not. This is the engine property `engine_actions.touch` (lever 2) is named for, and the
module is careful about the claim: it "does NOT make the history unevictable and this function's
name is the only claim it makes". StudyENG1c Part A's own touch probe is the instrument.

**M3.** If a history's blocks are evicted from the GPU pool under native offloading, then they are
placed on the 27 GiB host tier rather than discarded (D150, ENG1c). If a later request offers that
prefix, the engine satisfies it by transferring blocks over PCIe instead of recomputing them,
which the server reports as `prompt_tokens_by_source{source="external_kv_transfer"}` and as
`external_prefix_cache_hits_total`. A transfer at PCIe rates is cheaper than a prefill at the
committed 3.8 to 5k tok/s, so the reload's wall clock is below a cold rebuild's. This is
`engine_actions.plan_reload` (lever 3), whose trigger state the harness has never reached, which
is why the condition is created here and verified rather than observed.

**Where each link is grounded.** `FORMULATION.md`'s physical inertia: reconstruction cost grows
with context length, and a second KV tier changes the cost of a miss from recompute to reload.
M1 and M3 are measurements of that reconstruction cost under two different representations of the
same state; M2 is a measurement of which state survives to avoid paying it.

---

## 5. Step 2: instantiation, and the reads that consume each quantity

The value column is filled in BY THE RUN and lands in the JSON; what is pre-registered here is
the quantity, the read, and what would make the link ABSENT.

| causal link | implementing quantity | the READ that consumes it | ABSENT if |
|---|---|---|---|
| warm-ahead prefills the prefix | 12 prefill-only piece requests per rep, `max_tokens=1`, 11 frames each | the engine's own prefill; `M1.reps[].n_pieces` and each piece's `prompt_tokens` | a piece reports `cached_tokens` equal to its whole prompt, i.e. the piece did no work |
| the question offers the same prefix | the uuid-only reference parts, `bodies.image_part(path=None)` | vLLM `chat_utils` maps `uuid` to `multi_modal_uuids`, which REPLACES the computed mm hash and is the prefix-cache mm extra key (`cachekeys.py` docstring, with vLLM line cites) | the question's `prompt_tokens` differs from the build's, which would mean the prefix is not the same prefix |
| the engine reports reuse | `prompt_tokens_details.cached_tokens` | `backend.cached_tokens_of`, then `M1.warm_cached_fraction` | the field is absent: the preflight control catches this first and stops the run |
| a touch moves the eviction order | the full-prefix uuid-only probe, StudyENG1c's touch | vLLM's free-block LRU; observed through `M2.reps[].T_cached_tokens` against `U_cached_tokens` | TOUCH and NOTOUCH give the same winner, which is reported as the FAIL it is |
| pressure crosses the frontier | `M2.reps[].flood.tokens_charged` against `frontier.frontier_tokens` | the engine's block allocator | every repetition is `INDETERMINATE`, i.e. the pressure never landed in the window |
| eviction places KV on the host tier | `prompt_tokens_by_source|external_kv_transfer`, `external_prefix_cache_hits_total` | `classify_residency`, StudyENG1c's committed rule, on the twin AND on the timed request | neither counter family is in `/metrics`: M3 stops before any request |
| a reload is cheaper than a recompute | `reload_total_s` against `cold_full_total_s` and `cold_kv_total_s` | `M3.speedup_total_vs_cold_full` | no repetition verifies; then nothing is timed as a reload |

**Every one of these quantities is READ, not merely written.** The script's own
`result["requests"]` rows carry each one at its point of use, and the verdict functions are the
reads. That is the shape CLAUDE.md's write-only-field failures (`desired_tier`,
`RecallAction.representation`) lacked.

**The one quantity this leg CANNOT instantiate, named rather than worked around.**
`engine_actions.plan_warm_ahead` is unexpressible in the committed action space today:
`interface.validate_action` accepts a MATERIALIZE only for a session already warm or already
holding a pending question, so the first warm-ahead for a cold session is rejected for ever
(`reports/study_engine_actions.md` section 3). **M1 therefore shows that the ENGINE pays off a
warm-ahead when one is issued. It does not show that an arm can issue one.** The script issues it
directly over HTTP, which is legal for a confirmation and is not a policy run. This is recorded in
the JSON at `caveats.warm_ahead_expressibility`.

**The one declared violation of a committed convention.** M3's COLD_KV arm sends one device's
unchanged mm uuids under a SECOND `cache_salt`, so the frames stay in the mm processor cache while
the KV prefix chain becomes a new key. That is deliberately two salts on one device, which
`cachekeys.check_isolation` rejects by design. The role is excluded from the salt check BY NAME,
the exclusion and its reason are in the JSON, and the arm's uuids are still checked. Nothing else
is excluded.

---

## 6. Step 2b and Step 4: the switch reaching a decision, and the negative controls

**Step 2b, M2.** The TOUCH and NOTOUCH conditions differ in exactly one request: one
`touch_T`. Everything else, including the pressure size, the probe bodies and their order, is
identical. The decision the diff must move is which of two probes reports reuse. The script runs
both conditions and reports the 2x2 counts; identical counts in both conditions is an **ABSENT
LINK**, reported as `FAIL` with the reason "the NOTOUCH control shows the SAME winner as TOUCH",
never as a negative about the touch.

**Step 4, the negative controls, each of which is a condition in the run and not an afterthought.**

* *M2's mechanism is the touch.* Disabled by not touching. **Expected collapse: the OPPOSITE
  winner**, because without the touch U is the younger history. This is stronger than a collapse
  to the null: it is a reversal, and a design in which the control predicts a specific different
  outcome cannot be passed by a flood that is merely mis-sized.
* *M1's mechanism is the warm-ahead.* Disabled by the no-warm-ahead arm, which is the comparator
  itself. **Expected collapse: `cached_tokens` at or below one vLLM block.** If the cold arm
  reports substantial reuse, the salt is not isolating and the run says so.
* *M3's mechanism is the host tier.* Disabled two ways. COLD_KV removes the KV reuse while keeping
  the frames (same uuids, new salt): **expected collapse to a full prefill with no byte upload.**
  COLD_FULL removes everything (fresh device): **expected collapse to a full prefill with byte
  upload and vision encode.** The ladder of three isolates which part of the saving is KV.
* *The whole run's mechanism is prefix caching.* Disabled by the fresh-salt leg of the preflight
  control. **Expected collapse: zero reuse.** If it does not collapse, every measurement is
  void and the script stops.

**Step 3, the traced unit.** The unit of this study is one request. Every request the script sends
lands in `result["requests"]` as one row carrying: phase, role, device, session, frame count and
how many of those frames were bytes rather than references; the cache salt; HTTP status; TTFT and
total seconds; `prompt_tokens`, `cached_tokens`, `completion_tokens`; the external-hit token count
if the engine reports one; the `/metrics` delta for the rows where it is read, and the residency
class derived from it; and the mandatory `cache` block stating the condition, what was cached
before the request was sent, and whether a repeat could be served from cache. A reader can check
the arithmetic of any verdict by hand from those rows: that is what the trace requirement asks
for, and the script does not aggregate anything before it is inspectable.

---

## 7. Step 5: alternative explanations

**M1: "the warm arm is faster and reports reuse because it uploads no bytes, not because the
prefix was prefilled."** Distinguished by the quantity in the claim. Byte upload and vision encode
cannot produce `cached_tokens`: that field counts prompt tokens the engine did not compute. A
no-bytes request over a prefix the engine had never prefilled would report reuse near zero and
would in fact fail, because the uuids would not resolve. The TTFT gap IS confounded by the upload,
and is reported as such and not used for the headline.

**M1: "the reuse comes from the question text, not the history."** Distinguished by magnitude: the
history is 11,191 tokens and the question tail is a few dozen, and the pass rule asks for reuse at
or above half the prompt.

**M2: "the touched history survived because of where it happened to sit in the build order, not
because it was touched."** This is the alternative the NOTOUCH control exists for: the build order
is identical in both conditions, so if order were deciding it, both conditions would name the same
winner. **M2: "the probe itself kept it alive."** Both histories are probed, in the same order, at
the same point; the probe cannot favour one. **M2: "the pressure was sized to the answer."** The
two conditions take the same pressure and predict opposite winners, so no size favours the
hypothesis; and the sizing comes from a frontier measured before either condition ran.

**M3: "the reload is fast because it was still on the GPU."** This is the false pass that would
ship a mechanism whose trigger has never been observed, and it is exactly what the twin gate and
the self-classification of the timed request are there to exclude: a GPU-resident history
classifies `gpu`, not `host`, under StudyENG1c's rule, and a `gpu` classification discards the
repetition. **M3: "the reload is fast because the cold comparator is unfairly slow."** Two
comparators are reported, one of which (COLD_KV) keeps the frames in the processor cache and
differs from the reload in KV alone. **M3: "the counters say host but the transfer did not
happen."** Not distinguished by this run, and said so: the counters are the engine's own
accounting, and a run that wanted to go further would need the PCIe byte counter StudyRH5 used
(load bytes against host-hit tokens x 256 KiB). If the H100 has budget for a fourth phase, that is
the one to add.

**A limitation on all three, stated rather than buried.** The pressure traffic is TEXT, not
frames. It is a proxy for KV occupancy and LRU movement only, which is all M2 and M3 ask of it,
and it is **not** a proxy for fleet traffic composition. No number in this run is a fleet result.
Text is chosen because it costs no vision encode, which is what keeps the whole confirmation
inside a short break.

---

## 8. The flash dry validation, measured

`--dry` runs the entire decision path against `experiments/orchestration/live/fake_server.py`, the
committed CPU stub, with placeholder JPEGs in a temporary directory so the real body builder, the
real uuid conventions and the real wire form are all exercised on a box that holds no round-1
frames. Measured on flash, 2026-11-20:

| | |
|---|---|
| command | `python3 experiments/orchestration/live2/confirm_engine_actions_32b.py --dry --base-url http://127.0.0.1:8077 --served-model fake-32BI` |
| wall clock | 16.0 s |
| requests sent | 196, across preflight (3), M1 (42), frontier (25), M3 (45), M2 (81) |
| decision-rule self-test | 38 of 38 cases pass |
| D84 isolation over the run's own bodies | PASS: 134 devices, 134 distinct salts, 3,348 (device, frame) pairs, 3,348 distinct uuids |
| M1 / M2 / M3 | **NOT ESTABLISHED, all three** |
| dry verdict | PASS: the plumbing ran end to end and the script refused to conclude |

The filler request count is higher under `--dry` than it will be on the H100: the stub reports no
`prompt_tokens`, so the filler never calibrates its chars-per-token and every pressure request
stays at the small uncalibrated size. On a real server the first request calibrates and the rest
are about six times larger, which is the composition the duration estimate in section 1 is built
from.

**That the three verdicts are NOT ESTABLISHED is the result, not a failure.** The stub reports no
`prompt_tokens_details.cached_tokens`, models no prefix cache and exposes no offload counters, so
the only honest verdict is that nothing was established. The script returns exit code 0 on a dry
run only when no measurement is established: **a dry run that reported a pass would mean the
script fabricates one**, and that is the property the dry mode is for.

The 38 self-test cases exercise the rules themselves on fixtures rather than the plumbing: the
StudyENG1c residency classifier at each of its four outcomes and at its boundaries; the M1 pass
rule and its four ways of failing, including that an absent `cached_tokens` can never pass; the M2
outcome rule including its INDETERMINATE and NO EVIDENCE arms and that one block of reuse counts
as a miss; the M3 two-gate verification, including that a `gpu` twin does not verify a host
reload; the exact binomial tail; the D84 key conventions in both directions, including that
`check_isolation` rejects a shared salt; the metrics flattener against a real-shaped scrape; and
the committed usage readers' None-is-not-zero contract.

**Three defects were found by the dry run and fixed before anything was committed**, which is the
only reason to have a dry mode: (1) the D84 check failed on the script's own two deliberate
re-saltings, which is how the COLD_KV exclusion came to be named explicitly instead of discovered
on the H100; (2) the preflight's fresh-salt control reused one device id, making it a second salt
on one device rather than a clean second device; (3) the filler's first request sized its text
from an assumed 4 chars per token, which on a denser tokenizer would overshoot `--max-model-len`
and kill the whole run with an HTTP 400, so the first request is now small and calibrates the rate
before any large one is sent.

Failure paths were also exercised and are loud: a missing server, a wrong `--served-model`, a
`--duration-budget-s` too small to fit a phase, and a store without enough frames each stop or
skip with the reason and the fix in one line. A fifth path was exercised whole: the script was run
NON-dry against the stub over a constructed frame store, and it resolved a real committed EVAL
session's 124 frames, sent its three preflight requests, failed the positive control (the stub
reports no cached tokens), and stopped there with all three measurements NOT ESTABLISHED and the
control's verdict quoted as the reason. That is the behaviour a real server with prefix caching
off would get, and it costs three requests rather than a whole break.

---

## 9. What each outcome decides

**All three PASS** means "32B confirmation passed" and policy v5's engine actions hold on the
deployment stack, subject to the two caveats that travel in the JSON: warming ahead is not
expressible in the committed action space, and the harness's `KEEP_GPU_WARM` does not emit the
request that M2's engine property needs.

**M3 FAIL or NOT ESTABLISHED** does not block v5. The user's standing ruling on this row is that
v5 may go live with reload DISABLED and marked PROVISIONAL. The script distinguishes the two
outcomes because they are different findings and the brief is explicit that both a false pass and
a false fail are costly:

* **FAIL** means host residency WAS verified on at least one repetition and the reload was not
  faster. That is a real negative about the action, under CLAUDE.md Rule 2's "fired and did not
  help", and it is still not settled unless the controls moved (they do here, by construction:
  COLD_KV and COLD_FULL are the disabled conditions).
* **NOT ESTABLISHED** means the host-resident condition was never verified, or the channel to
  verify it does not exist. Under Rule 2 that is **INCONCLUSIVE, unexercised**, the same class as
  E36, E36b and E36c, and it is **not** evidence that reload-from-host is slow. The remedy is
  different too: it is a sizing or an instrumentation fix, not a policy decision.

**A side result this run produces whatever the verdicts.** The measured frontier settles, on the
deployment stack, whether the observable reuse window is the GPU pool plus the host tier or the
host window alone, which is a 1.57x question nothing committed answers; and the preflight dumps
one raw usage block, which confirms or replaces `engine_actions.EXTERNAL_HIT_KEYS`, a list the
module labels UNVERIFIED and whose docstring asks for exactly this ("the first H100 run on the
deployment stack must dump one raw usage block and confirm or replace this list").

---

## 10. After the run

The result JSON carries its own `_provenance` stamp per CLAUDE.md. The run does **not** itself
update `research/EXPERIMENTS.md`, `results/INDEX.md` or `research/STATUS.md`: the verdicts on the
StudyV5-ENGINE row are drafted for the user and not set, and the consistency check below is owed
before any of them is written.

**Results consistency check, planned against the quantities this run produces.** Check 1, the
cross-check against committed measurements: history prompt tokens against the committed 90 tok/img
and the 11,184-token nominal history; the frontier against the committed 62,944-token pool and the
27 GiB host tier; the cold rebuild rate against ENG1c's "about 11k tokens in about 2.1 to 2.2 s"
and RH5's 3.8 to 4.5k tok/s; and the reload advantage against RH5's 5.3x and 7.4x. Check 2,
physical plausibility: every implied token rate against those same curves, with anything more than
2x faster than the committed cold prefill treated as a caching artifact and not a finding. Check 3,
distribution sanity: per-repetition values are reported beside every median, because a constant
where a distribution is expected is the visible shape of breakage and these repetitions must not
agree to more precision than the engine varies. Check 4, definition audit: "history", "turn",
"touch", "reload" and "cold rebuild" each have one definition in this run and section 2 states it.
Check 5, claim linkage: M1 and M3 bear on physical inertia (reconstruction cost); M2 bears on
warm-state capacity; none of the three bears on semantic inertia and none is cited for accuracy.
Check 6, proxy validity: the text filler, declared in section 7. Check 7, validate the control:
the preflight positive control, in both directions, before anything else runs.

---

# RESULT, measured on the H100's deployment stack 19:30 to 19:39 (commit b685fbb)

Script `24c5492` unchanged, no flags, fresh round-1 server via `start_server`. Exit code 1.

**Headline: 32B CONFIRMATION NOT PASSED, because M2 is NOT ESTABLISHED. M1 and M3 both PASS.**

| measurement | verdict | the number |
|---|---|---|
| M1 warm-ahead raises cached tokens | **PASS** | 12-piece warm build of an 11,266-token history gives `cached_tokens` **11,152**; TTFT **0.088 s warm against 2.757 s cold**, residency gpu against cold |
| M2 touched survives, untouched evicted | **NOT ESTABLISHED** | 3 of 3 repetitions INDETERMINATE (`T_survived` 0, `U_survived` 0): the 190k-token flood did not land inside the one-history window |
| M3 reload-from-host beats rebuild | **PASS** | `verified_host_resident` true on the twin, twin and reload both classify `host`, external cached **11,168**, reload TTFT **0.134 s against a cold-KV 2.0 s** |

## M1 is the mechanism v5-rules rests on, and it holds at 31x

0.088 s against 2.757 s is a **31x** TTFT reduction on an 11,266-token history. v5-rules' dry proof
showed the WIRE FORM of this (the question carrying 2 frames instead of 330); **this is the engine
side of the same claim, and it is now measured rather than owed.** The caveat in the script still
stands and must travel: M1 shows the engine pays a warm-ahead off, NOT that an arm can issue one,
because the script issues it directly over HTTP while warming ahead became expressible in the
committed action space only with PATCH 1.

## M3 PASSED AGAINST MY EXPLICIT PREDICTION, and that is the most consequential line in this report

I told the H100 to expect `NOT ESTABLISHED` and to treat it as unexercised rather than a failure,
on the grounds that `believed_tier` is never `host` in 56 committed cells. **I was wrong, and wrong
in a way that matters more than being right would have.**

The two facts are both true and they are about different layers:

- **The ENGINE holds histories in the host tier and serves them from there**, verified on a twin
  before timing, and a reload is **0.134 s against a cold rebuild's 2.0 s, about 15x**.
- **Our COORDINATOR's belief never says `host`** in any committed cell.

So reload-from-host is **not an unreachable mechanism. It is a real, fast mechanism our policy
cannot currently trigger**, and the gap is in belief PROMOTION, not in the engine. Everything I and
session C wrote about this action being "unexercised" was right about our harness and wrong as a
statement about the capability. The correct reading is the opposite of the one I was heading for:
the 15x is sitting there unclaimed because the belief does not track the tier the engine is already
using.

That changes what the belief work is worth. It is no longer housekeeping on a dead field; it is the
only thing between the policy and a measured 15x on history restoration.

## M2 is unexercised, and the reason is in the JSON rather than in a guess

The flood was about 190,000 tokens in 42 s and did not evict exactly one of the two histories, so
both survived in all three repetitions and the control could not discriminate. That is Rule 2
**unexercised**, NOT evidence that touch fails. The script's own design anticipated this: its
control is a REVERSAL rather than a null, so a mis-sized flood yields INDETERMINATE instead of a
false asymmetry, which is why this came back honest rather than wrong.

**The fix is known and the data for it is in the same JSON.** M2 needs its pressure sized from the
MEASURED frontier the run recorded, rather than from a flood chosen in advance. That is a second
short break, and it is the user's call whether to spend one.

## Consequence for the gates, stated plainly

**"32B confirmation passed" requires all three, so it is NOT met.** Full v5 therefore fails this
condition in addition to the one it already failed, and the JSON's own `policy_consequence` records
the narrower true statement: **reload may go live.**

This changes nothing for v5-rules, which depends on M1 (passed) and not on M2 or M3, and stays
queued. It changes nothing about full v5's critical path either, because `MARGIN_CF` remains
unsettable: D154 (2) defines it in the objective's units while the gate's error is in seconds, and
no conversion is ruled. **Full v5 was already blocked by a ruling, not by this run.**

The preflight usage block is in the JSON, which settles `EXTERNAL_HIT_KEYS` (previously CONSTRUCTED
and unverified, and `engine_actions.py`'s own docstring asked for exactly this).

---

# M2 PASSES on the re-sized flood: 32B CONFIRMATION PASSED, all three

**H100, 23:13 to 23:18, fresh round-1 server, script e09391f, result e77fa65.** Exit code 0.

| condition | rep | T | U | outcome | flood |
|---|---|---|---|---|---|
| TOUCH | 0, 1, 2 | **gpu** | **host** | **T_SURVIVED** x3 | 47,027 / 47,131 / 46,982 |
| NOTOUCH | 0, 1, 2 | host | host | INDETERMINATE x3 | 47,048 / 46,962 / 47,097 |

**The touch moves a history between TIERS.** Touched stays in GPU, untouched falls to host, and with
no touch BOTH fall to host. That is the stronger statement the tier discriminator was built to
reach, and it is cleaner than "survives" would have been: survival was never the question, since M3
had already shown a host-resident history still serves at 0.134 s.

**The control behaves exactly as designed.** NOTOUCH shows NO asymmetry rather than the opposite
winner, which satisfies the pass rule's second branch and establishes that the touch is what moved
T. A flood that merely happened to be the right size would have produced the same winner in both
conditions.

The re-sizing was right and the bracketing contingency was not needed: 4 units of about 47,000
tokens separates the two histories, where 17 units at 190,328 had cleared both to cold.

## What all three passing does and does not establish, which is the part to carry forward

| | engine property | wired into the policy? |
|---|---|---|
| **M1** warm-ahead pays off, TTFT 0.088 s against 2.757 s cold, **31x** | **CONFIRMED** | **yes, since PATCH 1.** Before it, warming ahead was rejected by `validate_action` |
| **M2** touch keeps a history in GPU while an untouched one falls to host | **CONFIRMED** | **NO.** `coordinator._enact` handles `KEEP_GPU_WARM` by setting `desired_tier` (`coordinator.py:482`) and **emits no request** |
| **M3** reload from host beats rebuild, 0.134 s against 2.0 s, **15x** | **CONFIRMED** | **NO.** `believed_tier` is never `host` in 56 committed cells, so the trigger state never occurs |

**So all three engine actions are real on the deployment stack, and two of the three cannot be
triggered by our policy at all.** The engine can do everything v5's STATE half was designed around;
the gap is entirely in the coordinator. That is a much better position than the reverse would have
been, and it turns three separate "unexercised" notes into one statement with a number attached to
each.

**It also changes what `desired_tier` is.** CLAUDE.md cites it as the canonical write-only field,
three references and no read, and that is still true of the code. **But M2 has now measured the
engine property that field was supposed to drive.** So it is not dead code to delete: it is an
unclaimed tier promotion with a confirmed effect behind it. A write-only field whose mechanism is
proven is a different object from one whose mechanism is hypothetical, and the remedy is to wire it
rather than to remove it.

## Consequence for the gates

**The full-v5 condition "32B confirmation passed" is now MET.** Full v5 remains gated on the
cost-model gate alone, which cannot pass tonight: D158 (1) holds MARGIN_CF until all four held-out
cells run clean after the race fix, and two of the four were damaged. **So the remaining blocker is
a measurement rather than a definition or a mechanism**, which is the first time tonight that has
been true.
