# StudySH-EP: given the SAME episode context, does the 32B detect a coming crash better and earlier than the 4B?

**E-id:** StudySH-EP (design log D145). **PRE-REGISTRATION, written before any inference.** Nothing in
this report is a result. Every number below is either a committed measurement cited with its source, a
count of the request manifest, or a prediction labelled as one.

Flash contribution: the kit (manifest, store-extension encoder, runner, scorer) and this
pre-registration, all CPU only, no GPU, no model server, no inference. The one thing already computed
on data is the scorer's positive control, in section 8.

---

## 1. Hypotheses

| id | claim | the statistic that tests it |
|---|---|---|
| H1 | challenge AP: 32B > 4B with episode context, and the gap is LARGER than with one frame | mAP(32BI) - mAP(4BI) per condition, EVAL, paired clip bootstrap; and that gap minus C1's |
| H2 | earliness: the 32B's warning comes earlier than the 4B's at a matched false-alarm rate | per positive clip, lead = reference time - first instant above a DEV-set threshold; paired 32B - 4B difference |
| H3 | cost: with the episode kept warm, a multi-frame evaluation costs about a one-frame one | TTFT cold against warm, new (uncached) prompt tokens per request, KV tokens per episode, uplink bytes |

**Decision rule, fixed now.** If H1 and H2 both hold on EVAL with a bootstrap CI excluding 0 for an
episode condition, the cheapest condition that also satisfies H3 becomes the dashcam format. Otherwise
dashcams stay one-frame and the null is reported, classified under CLAUDE.md Rule 2 into one of
cancelled by geometry, unexpressible, unscorable, unexercised, or fired and did not help.

## 2. Data, and what is already committed

300 StudyD14b Nexar clips, 150 positive and 150 negative, split **90 DEV / 210 EVAL** by the committed
CTRL1 rule (`results/dashcam/ctrl1/d14b_split.json`: sha256 of the file name, lowest 30 percent to DEV,
stratified by label; clip overlap 0). Development seeds 0, 4, 5, 6 only; never seeds 1 to 3 and never
HOLDOUT. Nothing in this study is fitted on EVAL.

**Reference time.** Positives: `time_of_event`, as every committed Nexar study uses it. Negatives: the
committed challenge scorer's own matched fake event time at seed 0
(`study_e9c_challenge.fake_event_times`, sigma = 2.890460072101262 s, the sample sd of
`time_of_event - duration / 2` over the 150 positives, clipped to [4.5, duration]).

This needs stating plainly, because it was a stop condition and it was resolved rather than assumed.
StudyD14 and StudyD14b assign negatives **no reference time at all**, and StudyD3's assigned references
cover StudyD3's development clips, not these 300. The challenge scorer's matched fake event is the only
committed matched reference that exists over this clip set, and it is also the only choice under which
the headline metric is computable at all: the challenge scores each negative at `fake_event - h` for
h in {0.5, 1.0, 1.5} s, and those three instants lie inside the evaluated window only when the window
is anchored on that same time. The rule is lifted out of the committed script by AST and its source
sha256 is recorded, so an edit to it cannot pass unnoticed.

**Evaluated instants.** From 6 s before the reference time up to it, every 0.5 s, snapped to StudyD14b's
committed 0.25 s render grid: 13 instants per clip, the last of them at most 0.25 s before the
reference. One clip has a reference time small enough that two instants fall before the clip starts and
is evaluated at 11; the window is clipped, never the clip dropped.

A guarantee the scorer asserts rather than assumes: the challenge crops at `reference - h` always
coincide with an evaluated instant, because `6 - h` is a multiple of 0.5 s for every horizon and both
times snap to the same 0.25 s grid.

**Frames.** 2 fps, the live2 wire JPEGs of the D91 store
(`~/data/live2/jpeg/nexar_q90`, recipe PIL `save(format="JPEG", quality=90)` from the stored SMALL
768x432 PNG, no resize, recorded Pillow and libjpeg versions; byte-exactness to E10a is not claimed,
per D91). **Nothing is rendered and nothing is re-rendered:** StudyD14b already rendered the causal
frame (latest decoded pts <= target) for every 0.25 s grid point, so every instant this study needs is
already a row of its committed sha256 manifest.

**6,237 unique frames; 6,072 are already in the D91 store and 165 are not.** The encoder
(`encode_jpeg.iter_nexar`) walks the committed D14b **N = 1** rows and nothing else, so the store holds
one JPEG per decision time t >= 3.0 s and none below. EP-G reaches 10 s before the reference, so for 32
clips with a small reference time some context instants fall below 3.0 s. Their PNGs are rendered (they
are D14b N = 3 targets), so `sh_ep_encode_extra.py` adds exactly those 165 files with the committed
recipe function, verifies each source PNG against D14b's committed sha256 first, and refuses to
overwrite any existing file. Those 165 frames are the only ones in the study whose encode provenance
may differ from the rest, and the extension meta records the versions it ran with.

## 3. Conditions, identical for both models

| condition | frames carried at instant t | frames: min / max / mean | requests per model |
|---|---|---|---|
| C1 | the latest frame only | 1 / 1 / 1.00 | 3,898 |
| C3 | the last 3 frames, sliding | 1 / 3 / 3.00 | 3,898 |
| C6 | the last 6 frames, sliding | 1 / 6 / 5.98 | 3,898 |
| EP-B | append-only within 5 s blocks, reset at each block start | 1 / 10 / 4.69 | 3,898 |
| EP-G | append-only from (first evaluated instant - 4 s), capped at 21 frames = 10.0 s | 1 / 21 / 14.80 | 3,898 |

19,490 requests per model, 38,980 over both; 114,870 image parts per model. EP-B's blocks run from the
first evaluated instant: block 0 covers instants reference - 6.0 to reference - 1.5 (10 instants) and
block 1 covers reference - 1.0 to the last instant (3). A frame count below the nominal one is always a
clipped window at the start of a short clip, and every request records its realised count, the instants
it asked for and the instants that had no frame, so no count is ever inferred from the condition's name.

**Body.** The committed SH body: StudyD3's `QUERY` and `GEN` read out of
`experiments/dashcam/d3_infer_vllm.py` by AST and never retyped (sha256 of the extracted source is in
every run meta), header first, frames oldest first, question last. Greedy, max_tokens 8, seed 0,
top-20 logprobs. P(Yes) by StudyD3's own `yes_no` over the first token's top-20, score = log P(Yes).

Declared deviations over the committed SH body, each with its reason:

| deviation | why | precedent |
|---|---|---|
| more than one image | the study is about episode context | StudyD3 N = 3 and N = 9; but `live2/bodies.build_body(kind="monitor")` refuses it by design, so the runner builds the body itself |
| frame spacing 0.5 s | the brief's 2 fps grid; **C3 is NOT StudyD3's N = 3**, whose three frames span 3 s | none; stated as new |
| JPEG wire bytes, not PNG | the live2 wire format | D70, D91 |
| `cache_salt` and a per-image client `uuid` | cache isolation; one salt per (clip, condition, model run) and a uuid per (clip, condition, frame), so no episode can read another's warm state | D84 |
| `stream` true | H3 needs the first token timed | live2's own third declared deviation |
| the multi-frame header is count-free: `The following are consecutive dashcam frames, oldest first.` | ruled 2026-11-20 (section 4). StudyD3's header names the frame count, which makes a KV prefix unreusable AND makes the wording differ between conditions | none; **stated as a deviation from StudyD3's wording.** C1 keeps StudyD3's committed one-frame literal exactly |
| prefix caching and the multimodal processor cache ON; `--limit-mm-per-prompt image >= 21` | H3 is a claim about warm episodes, and EP-G carries 21 images | none; the committed SH stack runs with both caches OFF and the image cap at 9 |

Caching is a methodological parameter, not an implementation detail (CLAUDE.md), so the last row is the
one that needs a control rather than a note: section 8's positive control is what says what turning the
caches on did to the scores.

## 4. The header: ruled, 2026-11-20

StudyD3's header names the frame count and the span, and it sits **first** in the prompt. Under that
header an append-only episode has a different first token at every instant, so no KV prefix can ever be
reused and **H3 would be unreachable by construction** for EP-B and EP-G: the warm-path control would
report `cached_tokens` 0 everywhere and the finding would be "unexercised" in the Rule 2 sense, which is
a design failure and not evidence about episodes. This was found before any inference, which is what
Step 0 is for.

**The ruling: the count-free header for EVERY multi-frame condition.** C1 keeps StudyD3's committed
one-frame literal.

| condition | header sent |
|---|---|
| C1 | `The following is 1 dashcam frame.` (StudyD3's committed literal, byte for byte) |
| C3, C6, EP-B, EP-G | `The following are consecutive dashcam frames, oldest first.` |
| any request clipped to one frame at the start of a short clip | the one-frame literal |

**One flag, not two.** `--header-mode constant` is the ruling and the default, and it is correct for
**every** condition including C1: the manifest's `header_constant` field already resolves to StudyD3's
committed one-frame literal whenever the realised frame count is 1. Running C1 under `--header-mode
count` instead would send the same string today, but it would send a DIFFERENT string on any C3, C6,
EP-B or EP-G request that happens to be clipped to one frame at the start of a short clip, and the two
boxes would then disagree on those requests and fail the parity check in section 5b. Both boxes pass
`--header-mode constant` for the whole run.

It buys two things, and the second is why it applies to the sliding conditions too and not only to the
episode ones. First, an append-only episode now has a genuinely reusable KV prefix, so H3 is testable at
all. Second, **the wording can no longer confound a context comparison**: with StudyD3's header, a
difference between C3 and EP-G would be partly a difference in what the header said, since one would
announce 3 frames and 1 second and the other 21 frames and 10 seconds. Holding the text fixed makes the
frames the only thing that varies across conditions, which is the comparison the study exists to make.

The cost is a declared deviation from StudyD3's wording on the multi-frame conditions, recorded in
section 3 and in every run meta. StudyD3's `count` header stays frozen in every manifest row as the
non-default alternative and is not run; `--header-mode constant` is the default and the ruling.

## 5. Metrics

**Calibration (D6).** Platt scaling per (model, condition), fitted on the DEV challenge crops, which is
the metric's own label definition rather than a new one, and applied unchanged to EVAL.

Stated before it is fitted: **the calibration cannot move H1 or H2.** Average precision and a threshold
set at a DEV false-alarm quantile are both invariant under a strictly monotone per-arm transform, and
Platt scaling is one. It is fitted, applied and reported because the brief asks for it, and it is
reported as inert for the headline rather than as a step that did work.

**Headline: Nexar challenge AP** (arXiv 2503.03848) at the committed horizons 0.5, 1.0 and 1.5 s and
their unweighted mean, EVAL only, paired clip bootstrap, 2,000 resamples, seed 0 (StudyE9's own SEED and
NB). Horizon inclusion is the committed rule: h = 0.5 always; h > 0.5 only if
`time_of_event - time_of_alert > h`. These are not the challenge's test clips, so no number here is
leaderboard-comparable.

**Secondary, earliness.** Thresholds per (model, condition) set on **DEV negative instants** at
false-alarm rates 5, 10 and 20 percent; on EVAL, report the achieved false-alarm rate next to the target
and, per positive clip, the lead before the reference of the first instant above threshold; paired
32B - 4B difference with the same clip bootstrap. A clip an arm never fires on has no lead, so it enters
the paired difference only when both arms fire, and the counts each arm dropped out of the comparison
are reported beside the difference. Scoring a miss as a zero lead would convert it into a late
detection and move the difference in the direction of whichever arm misses more.

**Both split by suddenness**, StudyD3's own split at a 1.5 s lead (`time_of_event - time_of_alert`).

**Cost.** TTFT cold against warm, new (uncached) prompt tokens per request, KV tokens per episode,
uplink image bytes per episode.

## 5b. The deployment pair, and why it is cross-stack on purpose

| box | model | what its numbers are |
|---|---|---|
| jetson_orin | 4BI, the **full** set: all five conditions and all controls, under vLLM | the **deployed device** arm. Its scores are the device answers for H1, H2 and the rebuilt live workload, and its timings are H3's device-tier cost |
| h100nvl | 32BI only, under vLLM | the **deployed cloud** arm |

The comparison is labelled **deployed device (Orin 4BI, vLLM) against deployed cloud (H100 32BI,
vLLM)**, and it is **cross-stack BY DESIGN**. That phrasing is doing real work and is not a hedge. The
EXPERIMENTS.md sanity-check column requires any comparison across backends to be labelled
BACKEND-MISMATCHED, and that label exists for comparisons where the backend differs **by accident** and
the difference is therefore a confound nobody chose. Here the two stacks ARE the two conditions: the
question is what a device deployment detects against what a cloud deployment detects, so running the 4B
on device hardware and the 32B on cloud hardware is the treatment, not a flaw in it. Reporting it as an
accidental mismatch would misdescribe the design in the direction of making it look weaker than it is,
and reporting it as same-stack would misdescribe it in the direction of making it look stronger.

**What that costs, and what therefore has to be proved rather than assumed.** A capability gap and a
stack gap are no longer separable by construction, so the one thing holding the comparison together is
that both arms read the **same input**. The scorer checks it per request id and every failure is a stop
condition, not a note:

| checked per request | why it is a stop |
|---|---|
| equal prompt tokens | the brief requires it per request pair; unequal means the two arms are not reading the same prompt |
| identical header text | the ruling's header split must be the same on both boxes, or C1 diverges |
| identical frame sha256 list, in order | the same episode, the same bytes, the same order |

The multimodal processor settings must also match, because they set the image token count: the H100's
round-1 server runs `--mm-processor-kwargs {"size": {"shortest_edge": 4096, "longest_edge":
16777216}, "fps": 1.0, "do_sample_frames": false}` with `--trust-request-mm-kwargs`, and the Orin must
run the same. A difference there moves the prompt tokens and the parity check fails, which is the
intended outcome: it fails loudly rather than producing a gap that is partly a tokenizer difference.

**The processor settings are the study's settings, by ruling** (user, 2026-11-20): live2 round 1's
`--mm-processor-kwargs` are StudySH-EP's settings on **both** machines, because they are deployment
conditions and this study chooses the live dashcam format. C1 under those settings is therefore the
study's own one-frame comparator, whatever StudyD3 used. The first C1 prompt-token count is recorded,
and if it differs from the committed 378, consistency check 1 against StudyD14b is labelled
**CROSS-SETTING**, with the difference and its cause reported, and the study proceeds.

**Measured, so the label is not needed: the first C1 request reports 378**, on all 28 aborted requests
and the first requests of the real run. The round-1 settings give the committed 336 image pads at
768x432, so the C1 condition **is** the committed one-frame body and consistency check 1 stays
same-setting. This is worth stating as a measurement rather than leaving as an assumption, because it
was an open risk until the number came back: `shortest_edge` 4096 did not have to land on 336 pads.

**Per-frame cost, measured: 338 tokens, not the 342 the committed arithmetic predicts.** StudyD7's
378 at one frame against 1,062 at three gives 342 per frame, and the predicted EP-G maximum was 7,218;
the measured figures under the count-free header are 3,084 at 9 frames rising by a constant 338 per
frame to **7,140 at 21**. The 4-token difference is the committed figure's own header: StudyD3's N = 1
and N = 3 headers are different strings, so 342 conflated the per-frame image cost with a change in
header text. Holding the header fixed isolates the image cost at 338, which is the 336 pads plus the
two vision markers, and the count-free header at one frame would be 380 against the committed
literal's 378. The ruling's header therefore also bought a cleaner cost model than the committed one.

### 5b.1 Input identity, measured on both boxes before either swept

The frames reached the Orin by a relay the credential wall forced: flash pulled them from the H100's
store, the Mac host relayed flash to Orin with `scp -3`, and no key was added anywhere. A relay through
a third host is exactly where a silent corruption would arise, so it is checked twice, and the two
checks answer different questions.

| check | what it proves | result |
|---|---|---|
| every staged file against `sh_ep_wire_jpeg_sha256.jsonl.gz` (6,237 rows), joined on `rel_path` | the relay is intact | **6,237 of 6,237 byte-identical**, 0 missing, 0 mismatched; staged total 378,397,777 bytes exactly; all 6,237 hashes distinct |
| the five EP-G gate clips against the H100 precheck's `jpeg_sha256_sent`, joined on (`file_name`, `key`) | the Orin's bytes are the H100's wire bytes | **105 of 105 byte-identical**, 0 missing, 0 mismatched |

The byte total is corroborated independently, since rsync reported exactly 378,397,777 for the pull to
flash before any hashing was done.

**A join trap worth recording, because it produced a false failure and will produce others.** The
Orin's first pass at the second check reported 44 mismatches, and the cause was keying the lookup by
the frame `key` alone. **A frame key is a time index and is unique only WITHIN a clip.** Measured over
this study's own frame set: 6,237 frames carry only **782 distinct keys**, **439 of those keys are used
by more than one clip**, and the key `0015000` is used by **109 clips**, because the evaluated grid is
built on half-second instants and many clips hold a frame at exactly 15.000 s. Re-keyed by
(`file_name`, `key`) the check is clean, so the data was right throughout and the join was wrong.

The kit does not have this defect and that was verified rather than assumed: `sh_ep_runner.store_path`
resolves under the clip directory, the manifest keys its frame set by (`file_name`, `key`), and
`cachekeys.mm_uuid` carries the clip as `device_id`, so no frame identity anywhere in the kit rests on
the key alone. The wire manifest also carries `rel_path`, which is unique, and a join on that is safer
than a join on the pair.

### 5b.2 The Orin's server, and the one deviation that touches a result

Matched verbatim: the `--mm-processor-kwargs`, `--enable-prefix-caching`, `--enable-prompt-tokens-details`.
Not parity-relevant: `--mm-processor-cache-gb 4` against the H100's 128 and `--limit-mm-per-prompt
image 32` against 640, both caches ON and the cap above EP-G's 21; and KV offloading omitted, the Orin
being unified memory so the host pool is the same pool. Omitted as unavailable in vLLM 0.20.0:
`--trust-request-mm-kwargs`, which governs per-REQUEST overrides and has nothing to govern here,
because the runner sends no `mm_processor_kwargs` on any request.

**`--enforce-eager` and `--gpu-memory-utilization 0.4` do not touch H1 or H2 and DO touch H3.** They
leave the token counts alone, so parity and both headline metrics are unaffected. But eager mode
disables CUDA graph capture, and H3 is a claim about what a multi-frame evaluation COSTS on the device
that would run it. A device-tier TTFT measured in eager mode is therefore an **upper bound on latency
for a device deployment, not that deployment's cost**, and every H3 number from the Orin is labelled
that way. If eager mode is not required for memory or stability on this box, the H3 numbers are worth
re-taking without it; if it is required, the label stands and the bound is the finding.

### 5b.3 The EP-G gate: parity holds and H3's mechanism is already visible

The Orin's five-clip EP-G gate, 65 requests, before either box swept.

| gated quantity | result |
|---|---|
| per-request prompt tokens against the H100 precheck, same request ids | **65 of 65 exact**, at every frame count from 9 to 21: 3,084, 3,422, 3,760, ... 7,140 |
| `cached_tokens` on appended requests | present and above zero on **60 of 60**, and byte-identical to the H100's: 3,056, 3,392, 3,728, ... 6,768 |

Stop condition 3 is satisfied, and three things are settled by it rather than assumed. The
multimodal processor parity holds across two different vLLM builds with only the server-level
`--mm-processor-kwargs` matched. `--trust-request-mm-kwargs` was inert, as predicted from the runner
sending no per-request kwargs. And the uuid-only delta mode IS honoured on vLLM 0.20.0: every frame
contributes its 338 tokens although its bytes went out once, with none of the low-by-a-multiple-of-338
signature that a dropped reference would have produced.

**H3's mechanism is measurable already.** The marginal uncached tokens per appended instant are about
**366**, constant across episode length: the 338-token new frame plus a roughly 28-token recompute at
the prefix boundary. That is the quantity H3 is about, and it does not grow with the episode. It is a
gate observation on five clips, not the study's answer, and it is cited at that register.

**A cross-build reporting difference the scorer now handles, not a failure.** On the cold first instant
of each episode the Orin's vLLM 0.20.0 OMITS `cached_tokens`, where the H100's build emits 0. Both mean
no reuse, and an omission there is the one place a hit was impossible anyway. Counting it as a dead
instrument would have turned a build difference into stop condition 5, so `controls.warm_path` now
splits absence by whether the request could have hit at all: absence only on episode-first instants is
reported as a build difference, and the stop fires only when the field is absent where reuse was
possible. Here the instrument reads on 60 of 65 and is silent on exactly the 5 genuine misses, so
**stop condition 5 is not triggered**.

**One kit bug, found by the gate and fixed.** `--greys 0` did not disable the grey control: the repeat
count was `max(1, greys // len(counts))`, which is 1 at zero, and the loop then built a grey body with
no bytes, sent `GREY.mp4` to `store_path` and raised `FileNotFoundError`. It crashed after all 65 real
requests had been written, so no gate data was lost. The grey loop is now skipped outright when
`--greys 0`.

## 6. Mechanism verification, Steps 0 to 5, before the sweep

**Step 0, what would make this run uninterpretable.** Five checks were run and three of them came back
"wait", which is the point of running them.

| # | asked | answer |
|---|---|---|
| 1 | is there a committed reference time for the negatives? | **NO.** Resolved in section 2 with the challenge scorer's own matched fake event, which is the only committed one over these clips and the only one the headline metric can be computed under. |
| 2 | are all the frames in the JPEG store? | **NO**, 165 of 6,237 are below the committed 3.0 s decision grid. Resolved by a listed, recipe-identical store extension (section 2). |
| 3 | can the mechanism H3 claims be reached at all? | **NOT under StudyD3's header** (section 4). Open ruling; the three sliding conditions do not depend on it. |
| 4 | can the committed SH body carry an episode? | **NO:** `build_body(kind="monitor")` refuses any body with more than one frame. The runner builds the body from the committed `QUERY` and `GEN` instead, extracted by AST. |
| 5 | does the server configuration this study needs move the committed scores? | unknown until the run; this is exactly what section 8's positive control measures, and it is a STOP if it fails. |

**Step 1, the causal chain.** If the semantic component of Context Inertia is real
(FORMULATION.md, the semantic component of Context Inertia), then a cheaper representation of a dashcam
episode discards task-relevant information, and a model with more capacity extracts more from the same
retained information. So (a) giving both models the same multi-frame episode rather than one frame
should raise both, (b) the larger model should gain more, because the extra evidence is the subtle,
short-lived kind its capacity exists to read, and (c) the gain should show up first as earlier
detection at a matched false-alarm rate, because an approach visible across frames is visible before it
is visible in any single frame. The cost link is separate: if the episode is kept warm, the marginal
work per evaluation is the new frame only, so the physical component of Context Inertia does not grow
with the episode and the format is affordable.

**Step 2, each link instantiated.** The implementing quantity, where it is read, and what makes it
non-zero:

| link | implementing quantity | read site | non-zero and varies? |
|---|---|---|---|
| episode context reaches the model | image parts per request | the wire body; `n_frames` and `n_new_images` per record | 1 to 21 by condition, recorded per request |
| capacity differs | the two pinned models | the endpoint's `model` | 4B against 32B, the committed pair |
| evidence changes the score | log P(Yes) from the first token's top-20 | `yes_no`, the committed function | to be measured; the grey control says what a constant input gives |
| frame ORDER carries meaning | the shuffled-order control | `controls.shuffled_minus_ordered` | **to be measured, and this is the link most likely to be absent:** if shuffling the context changes nothing, the episode conditions are bags of frames and H1's mechanism is not sequence reading |
| the episode is warm | `cached_tokens` on an append-only request | `controls.warm_path`, presence separated from zero | **unreachable under the `count` header** (section 4); that is why section 4 exists |

**Step 2b, the switch reaches a decision.** The conditions differ in the frames they carry, which is
visible in the request manifest before any inference: 3,898 requests per condition with distinct frame
multisets, and the frame keys and their sha256s are recorded per request. The run's own first check is
that C1 and C6 scores differ on the same clip and instant.

**Step 3, one traced unit.** One clip, one condition, all 13 instants, with the frame keys sent, the
new against cached prompt tokens, TTFT, the score, the challenge crops used, and the lead at each
threshold. To be pasted into section 9 from the first completed cell, before the sweep is scored.

**Step 4, negative control.** Grey frames at every frame count the run uses: a constant input must give
a constant score, and if it does not, the score is reading something other than the frames. Second
negative control: the shuffled-order subset, which disables the sequence information while holding the
frame multiset fixed.

**Step 5, the alternative explanation.** A 32B-over-4B gap that grows with frame count could be
produced by (a) the larger model reading the approach across frames, the claimed mechanism, or (b) the
larger model simply being better calibrated on more image tokens, with no use of the temporal
relation at all. The shuffled-order control distinguishes them: under (a) shuffling degrades the 32B
more than the 4B; under (b) shuffling changes neither. If the shuffled difference is at the numerical
floor for both models, the two are not distinguished and the report says so.

## 7. Stop conditions

Any one of these stops the run or the scoring, and is reported rather than worked around.

1. The scorer's positive control misses a committed StudyE9c value by more than 1e-9.
2. More than 1 percent of requests fail after retries, or more than 1 percent return neither Yes nor No.
3. A prompt-token mismatch between the two arms on the same request id, or a header or frame-sha256
   mismatch: they are then not reading the same episode and no gap between them is a capability gap.
   This matters more here than in a same-stack study, because the two arms are two deployments
   (section 5b) and input identity is the only thing the comparison rests on.
4. A grey control whose score is not constant at a given frame count.
5. `cached_tokens` absent from every record: the warm-path instrument never reads, so H3 is unscorable
   as posed and must be re-posed, not reported.
6. A foreign process on the run's GPU, or a server-log error before the requests complete.

Not a stop, by ruling: a first C1 prompt-token count other than the committed 378. It is recorded, and
consistency check 1 against StudyD14b is then labelled CROSS-SETTING rather than abandoned. The
measured value is 378 (section 5b), so the label is not needed.

## 8. The positive control, already run

`sh_ep_score.py` implements the challenge AP itself, because this box has no sklearn and the committed
scorer calls `average_precision_score`. An implementation of a committed metric is worth nothing until
it reproduces that metric's committed numbers, so the scorer rebuilds StudyE9c's crops from the
committed StudyD14b trace and recomputes the zero-latency arms before it scores anything. The crop rule,
the horizon inclusion rule, the matched fake reference and the grid index are all lifted out of the
committed scripts by AST.

| arm | this scorer | committed StudyE9c | max absolute difference, mAP and all three horizons |
|---|---|---|---|
| 4BI N=1, zero latency | 0.5223157117 | 0.5223157117 | 5.55e-17 |
| 32BI N=1, zero latency | 0.6367561946 | 0.6367561946 | 1.11e-16 |
| 32BI N=3, zero latency | 0.6493273374 | 0.6493273374 | 5.55e-17 |
| 4BI N=3, zero latency | 0.5331714751 | 0.5331714751 | 1.11e-16 |

Positive clips per horizon 150 / 106 / 66, matching the committed counts. Every arm agrees to one unit
in the last place, so the AP, the crops, the horizon inclusion and the matched negative reference in
this scorer are StudyE9c's own and not a re-implementation. **PASSED**, and it runs again, first, on
every scoring pass.

## 9. Handoff notes

**h100nvl, the deployed cloud arm, 32BI only.** (1) The store extension first, before any inference: `sh_ep_encode_extra.py --dry-run`
then without it, on the frame host, with `--src ~/data/dashcam/d14b_frames/small:~/data/dashcam/d14_frames/small`
and `--store ~/data/live2/jpeg/nexar_q90`. If the Pillow or libjpeg version differs from the store's
original encode run, report it: those 165 frames are then the only ones whose encode provenance differs.
(2) Server: prefix caching ON, the multimodal processor cache ON, `--limit-mm-per-prompt image` at 21 or
more; everything else the committed stack. Record the exact command line in the run meta. (3) `--model 32BI`, all
five conditions, DEV and EVAL, `--header-mode constant` (the default and the ruling, for every
condition including C1), `--shuffle-control`. 19,490 requests. The runner is resumable. (4) Report the
first C1 request's prompt-token count before the sweep: it must be the committed 378.

**The store has two layouts, and the runner reads both.** `encode_jpeg.py` writes one flat file per
frame_ref, `frames/<clip>.mp4__t<t>.jpg`, which is what the manifest's `store_files` are built from.
The live store on the frame host is laid out `frames/<clip>/t<t>.jpg`, and this study's own 165-frame
extension wrote flat names beside those clip folders, so the store now mixes the two and nothing was
overwritten. `sh_ep_runner.store_path` resolves either layout and raises rather than substituting if a
frame is in neither. That is deliberately preferred to depending on a symlink view: a view can be
stale or incomplete without the run noticing, and the per-frame sha256 check still has the last word.

**jetson_orin, the deployed device arm, the full 4BI set.** Stage the 6,237 frames, 6,072 from the D91 store plus the 165 the extension adds, after
the H100 has written them, so both boxes read byte-identical input. Pull with dereferencing
(`rsync -aL`) so the Orin's copy is plain files, then verify every one against the committed D14b
manifest before sending a request. The full 4BI set, all five
conditions and all controls, same runner, `--header-mode constant` for every condition including C1,
and **the same `--mm-processor-kwargs` as the H100**, because those settings set the image token count
and the parity check in section 5b will fail without them. Its scores are the device answers for H1, H2
and the rebuilt live workload, and its timings are H3's device-tier cost.

**Both.** Every record carries its own `host`, so the two arms join by `request_id` and separate by
host without reference to a file name. The stop conditions in section 7 apply on both boxes, and the
input-identity checks in section 5b can only be computed once both runs exist, so neither box's numbers
are read before the other's have landed.

## 9b. What the warm path did, measured before the sweep

The H100's five-clip EP-G pre-check (`results/dashcam/study_sh_ep/h100/sh_ep_precheck_EPG_32BI.jsonl`,
78 records, 0 errors, count-free header) reports `cached_tokens` **present in every record and above
zero on every appended request**, from 3,056 to 6,768 against prompt totals of 3,422 to 7,140. So the
warm path is exercised and H3 is reachable, which is exactly what the count header would have prevented:
under it the same check would have read zero everywhere and H3 would have been unscorable as posed.
This is the Step 2 link that was marked unreachable in section 6, now marked live.

Also recorded: 28 C1 requests went out under the count header before the ruling landed and are set
aside as `ABORTED_count_header_*` under run tag `shep1`, with the real run restarted as `shep2`. Their
cache cannot reach the real run, because both the `cache_salt` and every image `uuid` are keyed by the
run tag, so no `shep2` request can hit a `shep1` entry. All 28 reported 378 prompt tokens.

## 10. Open at the time of writing

- Step 3's traced unit, to be pasted from the first completed cell before any sweep is scored.
- The run's own consistency check 1 (this study's C1 against the committed D14b N = 1 scores, which
  differ by the JPEG wire format under D70: 30 to 40 percent of individual Nexar scores move by more
  than 1 nat, so the comparison is distributional and not per request).
