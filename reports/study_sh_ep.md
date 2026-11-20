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

### 5b.4 The cost-under-load cell (user step 3), pre-registered before it runs

EP-G and C1 on 50 clips, as a concurrent client against the live2 round-1 server while a 16-device
dashcam-and-robot background runs on the same GPU. Reports TTFT and `cached_tokens` per request. The
kit gained two flags for it, `--clips-from-meta` and `--served-model`, so both boxes still run one
file.

| choice | value | why it is not a guess |
|---|---|---|
| the 50 clips | the pre-registered `shuffle_control_clips` subset | already in the manifest meta, 25 positive and 25 negative, all EVAL. Gives **1,300 requests** (2 conditions x 13 instants x 50 clips) and 10,257 image parts |
| background workload | two-type dashcam : robot at **50:50** | the committed default: `run_live2_real.py --ratio` defaults to `50:50`, and D103 (f) defines that string as the dashcam : robot ratio the scorer reads. Not the frozen grid's 40:40:20, because the user said dashcam : robot |
| background arm | `b7-edf-feasibility`, 16 devices, tight memory | the user's step 3 names b7 and 16 devices |
| served name | `--served-model 32BI` | the round-1 server's served names are pinned and it refuses any extra flag, so the runner's HF id would 404 |
| condition order | EP-G and C1 **interleaved by clip**, each episode contiguous | the runner already sorts by (clip, condition, instant), so per clip it sends C1's 13 then EP-G's 13. Interleaving matters: run back to back and any drift in background load lands entirely on one condition, which would be read as a condition effect |
| cache isolation | run tag `shep2-load` | both the `cache_salt` and every image `uuid` are keyed by the run tag, so no load-run request can hit an entry from the unloaded `shep2` run. Each episode still warms on itself, which is what makes the comparison a like-for-like |
| background length | at least as long as the client, so about 2,400 s for 1,300 requests at 1 to 2 s each, with the client started after the background reaches steady state | a client that outlives its background measures an emptying queue, and one that starts at t=0 measures a warm-up |

**A prediction, stated before the run rather than after it.** Section 17 of
`reports/study_frozen_test.md` measures the frozen grid pushing 5,604,554 prompt tokens through a
62,944-token KV pool in 1,200 s, which is **89 pool turnovers**, and that is why the grid's own
`prefix_cache_hits` is 0. An EP-G episode under that kind of background has 0.5 s between its
instants and is competing with the same traffic, so **`cached_tokens` should fall sharply under load,
and may reach zero**, even though it is 3,056 to 6,768 unloaded. If that happens it is the finding,
not a failure: it would say H3's warm-episode saving is contingent on the episode's prefix surviving
the background, which is a memory-capacity claim and not a latency one, and it is the same conclusion
sections 15 and 16 reached offline. If `cached_tokens` instead holds up, that is evidence the pool is
not as contended as the grid's turnover figure suggests, and worth more than a confirmation.

Either way the number to read first is `cached_tokens` per request, not TTFT: TTFT under load mixes
queueing with prefill, and only `cached_tokens` says whether the prefix survived.

### 5b.5 The load-cell prediction, REVISED before the run on the right timescale

The prediction in 5b.4 said `cached_tokens` should fall sharply under load and might reach zero. **It
was wrong, and the error was a timescale, not an arithmetic slip.** It argued from section 17 of
`study_frozen_test.md`, where the frozen grid pushes its KV pool over 89 times in 1,200 s, and
inferred that an episode's prefix would not survive. But 89 turnovers per run is the wrong rate to
compare an episode against. The quantity that matters is how much background traffic passes between
two CONSECUTIVE instants of one episode, which are 0.5 s apart.

Measured on the ruled background, the committed `b7-edf-feasibility` three-type cell at 16 devices:

| quantity | value |
|---|---|
| background prompt tokens in 1,200 s | 5,489,609 over 13,558 requests |
| background token rate | 4,575 tokens per second, 7.3 percent of the 62,944-token pool per second |
| **one full pool turnover** | **13.8 s of background traffic** |
| background tokens between two EP-G instants, 0.5 s | **2,287, or 3.6 percent of the pool** |
| background tokens across one whole 6 s episode | 27,448, or **0.44 turnovers** |

So an episode lives well inside one pool turnover, and section 17's figure applies to the frozen
grid's OWN reuse opportunities, which are separated by 34 to 350 s, that is 2.5 to 25 turnovers. The
two situations differ by three orders of magnitude in the gap being bridged.

**The revised prediction, pre-registered here before the run.** `cached_tokens` should LARGELY SURVIVE:
EP-G should stay mostly warm, with a median near its unloaded 4,736. What should degrade is TTFT,
through queueing rather than through recomputation. H3's claim is a RATIO, EP-G against C1, and the
ratio should stay near its unloaded 1.16x if the warm-episode saving is real under contention. A
reading where both TTFTs rise together and the ratio holds supports H3 more strongly than the
unloaded numbers do, because it shows the saving is not an artifact of an idle engine.

**And the failure mode worth watching is a burst, not an average.** The background's robot recalls run
up to 21,720 prompt tokens, which is 34 percent of the pool in a single request. The average rate says
the prefix survives; a few large recalls arriving together could still evict one. So if
`cached_tokens` does collapse, the thing to check is whether the misses CLUSTER in time with the
background's large recall requests, rather than being spread uniformly. Uniform misses would mean the
average-rate argument above is wrong; clustered misses would mean it is right and the tail is what
bites. Those two have different consequences for a deployment, and the run can distinguish them.

**On ordering, the H100 is right and I overstated my own error.** By-clip interleaving IS
truncation-robust: a cut falls inside at most one clip, so every completed clip carries both its C1
and its EP-G episode, and truncation then costs whole clips from both conditions equally. The 11
all-C1 records say only that the saturated run never finished its FIRST clip, each C1 request taking
about 40 s. That is a magnitude problem, not an ordering flaw, and running EP-G first as two separate
invocations would have put the two conditions in different background phases, which is the drift
exposure the by-clip design exists to avoid. The runner stays as it is.

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

## 11. Interim results, 2026-11-20 (A6000; the 4B has C1 and C3 only)

Committed scorer, committed crops, EVAL headline, paired clip bootstrap 2,000 at seed 0. The
positive control passes first, as always: all four StudyE9c zero-latency arms reproduced to one unit
in the last place. **The 4B has run C1 and C3 only**, so every 32B-minus-4B figure below is at those
two conditions, and the episode conditions are so far 32B-only. Nothing here is a decision rule
verdict; section 1's rule is applied once the pairs are complete.

### 11.1 Confirming the planner's quick pass, and where it differs

| quantity | planner, rank-based nearest instant | this run, committed scorer | verdict |
|---|---|---|---|
| 32B minus 4B, C1 | +0.098 [+0.04, +0.16] | **+0.1002 [+0.0378, +0.1665]** | **confirmed** |
| 32B minus 4B, C3 | +0.088 | **+0.0980 [+0.0246, +0.1752]** | confirmed in sign and significance, 1.0 pp higher |
| 32B C3 minus C1 | -0.028 | **-0.0277 [-0.0911, +0.0324]** | **confirmed** |
| 32B C6 minus C1 | -0.026 | **+0.0025 [-0.0687, +0.0683]** | sign differs, both within noise |
| 32B EP-B minus C1 | -0.005 | **+0.0054 [-0.0485, +0.0520]** | sign differs, both within noise |
| 32B EP-G minus C1 | -0.064 | **-0.0316 [-0.1248, +0.0507]** | same sign, half the magnitude |
| all four condition CIs include 0 | yes | **yes** | **confirmed** |
| 32B TTFT p50, C1 | 0.130 | **0.1302** | **confirmed** |
| 32B TTFT p50, EP-B | 0.132 | **0.1324** | **confirmed** |
| 32B TTFT p50, C6 | 0.378 | **0.3792** | **confirmed** |

The TTFT figures agree to three or four significant figures, so the two passes are reading the same
runs. The AP differences are explained by the crop rule rather than by the data: the committed scorer
applies the challenge's horizon-inclusion rule, so a positive clip enters h = 1.0 and h = 1.5 only if
`time_of_event - time_of_alert > h`, giving **150 / 106 / 66** positives per horizon, while a nearest
instant pass over all positives uses 150 at every horizon. That reweights the three per-horizon APs
and moves mAP by a few points, unevenly across conditions. **No headline conclusion changes**: the
32B beats the 4B at both available conditions, and no episode condition beats C1.

### 11.2 H1: the first half holds, the second half does not

**32B over 4B is real at both conditions**: +0.1002 at C1 and +0.0980 at C3, both CIs excluding zero.

**The gap is not larger with episode context.** The C3-minus-C1 difference of the gap is
**-0.0023 [-0.0584, +0.0531]**, and within the 32B no condition beats one frame:

| 32B condition | mAP | minus C1 | CI |
|---|---|---|---|
| C1 | 0.6381 | reference | |
| C3 | 0.6104 | -0.0277 | [-0.0911, +0.0324] |
| C6 | 0.6406 | +0.0025 | [-0.0687, +0.0683] |
| EP-B | 0.6435 | +0.0054 | [-0.0485, +0.0520] |
| EP-G | 0.6065 | -0.0316 | [-0.1248, +0.0507] |

Four conditions, four intervals containing zero, two of them negative. On the evidence so far,
**more frames of the same episode do not make the 32B better at this task**, and the largest frame
count, EP-G at up to 21, is the worst of the four. H1's second half is not supported, and it cannot
yet be called a real negative: the 4B's episode conditions are still running, and the Rule 2
classification waits for them.

### 11.3 H2: the leads are indistinguishable; what the 32B wins is whether it warns at all

Thresholds set on DEV negative instants, applied to EVAL. The paired lead difference is within noise
in five of six cells, the exception being C3 at a 5 percent false-alarm rate (+0.82 s [+0.33, +1.36]).

What is not within noise is the detection count:

| cell | 32B detects | 4B detects | 32B achieved FAR | 4B achieved FAR |
|---|---|---|---|---|
| C1, far 5 % | **56** | 36 | 0.034 | 0.043 |
| C1, far 10 % | **71** | 63 | 0.062 | 0.087 |
| C1, far 20 % | **89** | 77 | 0.123 | 0.185 |
| C3, far 5 % | **60** | 32 | 0.024 | 0.035 |
| C3, far 10 % | **80** | 41 | 0.071 | 0.057 |
| C3, far 20 % | **88** | 72 | 0.128 | 0.132 |

Two things follow, and the second is a caveat against the 32B.

The paired lead comparison is computed only on clips where **both** arms fire, which at C3 far 5 % is
25 of 150 positives, because the 32B fires on 35 clips the 4B misses. So the lead columns describe a
small, selected subset, and the counts beside them are the larger effect. The honest statement of H2
on this evidence is **not** that the 32B warns earlier, it is that **at a matched false-alarm target
the 32B warns on more clips, and warns no later on the clips both catch**.

The caveat: the 4B's **achieved** EVAL false-alarm rate is above the 32B's in five of six cells, in
one case 0.185 against 0.123 at a 0.20 target. The operating points are therefore not perfectly
matched on EVAL and the mismatch favours the 4B, so the 32B's detection advantage above is a lower
bound, not an inflated one.

### 11.4 H3 is the strongest result in the study so far

| 32B condition | frames at the last instant | TTFT p50 | against C1 | warm requests | median cached tokens |
|---|---|---|---|---|---|
| C1 | 1 | **0.1302** | 1.00x | 0 of 3,898 | 0 |
| EP-B | up to 10 | **0.1324** | **1.02x** | 2,698 | 1,024 |
| EP-G | up to 21 | **0.1514** | **1.16x** | 3,595 | 4,736 |
| C3 | 3 | 0.2357 | 1.81x | 3 | 0 |
| C6 | 6 | 0.3792 | 2.91x | 23 | 0 |

**With the episode kept warm, a 21-frame evaluation costs 1.16 times a one-frame one.** The same
information sent as a sliding window costs 1.81x at three frames and 2.91x at six. That is H3 as
posed, and the contrast between EP-G and C6 is the mechanism rather than a coincidence: EP-G carries
more than three times C6's frames at 40 percent of its TTFT, because its prefix is reused while C6
rebuilds a different window every instant.

The gate's marginal figure holds at full scale: EP-G's median new prompt tokens is **372** against a
median **4,736** cached, so each added instant pays for its own frame and almost nothing else.

**This matters most where H1 is weakest.** Episode context is nearly free, and on current evidence it
also buys nothing in accuracy. A format that costs 1.02x and gains 0.005 mAP is not a bargain, it is
an irrelevance, and the decision rule in section 1 is the right way to say so once the 4B's pairs land.

### 11.5 The cost-under-load cell did not produce a measurement, and the ordering was my error

The H100's load step was **stopped by the operator as saturated**, correctly, and is not a
measurement. The two-type 50:50 background at 16 devices saturated the engine on its own: background
TTFT p50 **47 s** over its last 400 requests, 38 requests running at once, two non-200s. The client
saw C1 TTFT of 36 to 46 s against 0.1302 s unloaded and completed **11 of 1,300** requests.

**All 11 were C1 and none was EP-G**, so the cell says nothing about the question it exists to ask.
That part is my fault, not the engine's. I specified interleaving by clip, and the runner sorts by
(clip, condition, instant), which puts C1 before EP-G inside every clip. That ordering is robust to
background **drift**, which is what I designed it for, and defenceless against background
**truncation**, which is the binding risk under saturation. EP-G should go first inside each clip, or
the two should alternate by clip, so that a truncated run still carries both conditions.

My pre-registered prediction in 5b.4, that `cached_tokens` would fall sharply under load, is
therefore **untested**. The 11 records all show cached 0, but C1 is cold by construction, so they
carry no information about it.

The background also needs resizing, and the committed numbers say by how much. D144 records the
three-type 40:40:20 dashcam offered load at 16 devices as **73 percent** of the committed 32B peak,
and 20 devices as 97 percent and saturated. A two-type 50:50 cell raises the dashcam share by
50/40, which puts 16 devices at roughly **91 percent** of peak before the client's own 1,300 requests
are added, so saturation is what the committed arithmetic predicts. That is a **CONSTRUCTED** scaling
from two committed figures, not a measurement. Scaled the same way, 12 devices sits near 68 percent
and leaves headroom; the alternative is the frozen grid's own 40:40:20 cell at 16 devices, which is
**measured** not to saturate (13,562 requests, 0 errors, scheduling lateness p99 0.15 ms). The choice
between keeping the user's stated two-type shape at fewer devices and keeping 16 devices at the
proven three-type mix is the user's.

### 11.6 Controls

| control | result |
|---|---|
| positive control | **PASS**, all four committed StudyE9c arms to 1 ulp |
| prompt-token parity across the deployment pair | **7,796 pairs, 0 mismatched** |
| grey frames | constant to the engine's logprob resolution: every grey score is an exact multiple of **1/8 nat** at P(Yes) about 8e-9, with `mass_no` 1.0 in all 280 rows. Worst spread 0.25 nats, one or two representation steps |
| shuffled context order | **mean absolute change 2.09 nats, max 15.1** over 1,298 pairs, so frame order carries real information and the episode conditions are not bags of frames |
| warm path | exercised on C3, C6, EP-B and EP-G; C1 has no reusable prefix by construction |
| stop condition 5 | **does not fire** |

Two of these controls failed on my first pass and both failures were mine, not the study's.

The grey control failed on **exact equality**. A score of log P(Yes) at the bottom of a top-20 list is
quantised, and demanding bit equality of it is the wrong test; the right one is constancy of the
answer plus a spread inside the quantum, and the quantum is now measured and reported rather than
assumed.

The warm-path control fired **stop condition 5 on the 4B's C1**, where every request is cold by
construction. The cause is a build difference: measured over 7,796 records, the H100's build emits
`cached_tokens` 0 on a cold request 13,171 times, while the Orin's vLLM 0.20.0 emits a zero **never**
and omits the field instead, reporting it only on the 3 requests that hit. For that build absence IS
zero and no read is missing, so the stop now fires only for a build that reports neither zeros nor
hits anywhere. Left unfixed, the study would have stopped on a difference of spelling.

### 11.7 DEV beside EVAL, for contrast only

DEV is where the calibration is fitted, so these are not held-out numbers and are never the headline.
They are shown because a large EVAL-minus-DEV gap would mean the split is doing more work than the
condition.

| arm | EVAL | DEV (45 + 45 clips) | EVAL minus DEV |
|---|---|---|---|
| 32BI C1 | 0.6381 | 0.6305 | +0.008 |
| 32BI C3 | 0.6104 | 0.6963 | **-0.086** |
| 32BI C6 | 0.6406 | 0.6643 | -0.024 |
| 32BI EP-B | 0.6435 | 0.6139 | +0.030 |
| 32BI EP-G | 0.6065 | 0.5788 | +0.028 |
| 4BI C1 | 0.5379 | 0.5407 | -0.003 |
| 4BI C3 | 0.5125 | 0.5299 | -0.017 |

Six of seven arms sit within 0.03 of their DEV value, which is reassuring at 90 DEV clips. The
exception is **32B C3 at -0.086**: C3 is the one condition whose ranking would change materially if
DEV were the headline, and it is also the condition whose gap figure differs most from the planner's
pass. Both point the same way, that C3's three-frame sliding window is the least stable arm here, and
it is worth remembering when its numbers are read.

### 11.8 What is still missing

The 4B's C6, EP-B and EP-G, which are running. Until they land, the pairs exist only at C1 and C3, so
H1's episode half rests on 32B-only contrasts, and the section 1 decision rule is not applied. The
cost-under-load cell needs a background the engine can sustain. The RefSpatial and single-shot work
queued for the Orin is independent of all of this.

### 11.9 Update, 2026-11-20: the 4B's C6 lands, and H1's second half turns on the SMALL model

The Orin's C6 arrived (0303be7), giving a third paired condition. It changes the H1 picture, and not
in the direction the hypothesis anticipated.

| condition | 32B minus 4B | CI | that gap minus C1's | CI |
|---|---|---|---|---|
| C1 | +0.1002 | [+0.0378, +0.1665] | reference | |
| C3 | +0.0980 | [+0.0246, +0.1752] | -0.0023 | [-0.0584, +0.0531] |
| C6 | **+0.1622** | [+0.0995, +0.2241] | **+0.0620** | [-0.0009, +0.1163] |

**The gap at six frames is 62 percent larger than at one frame**, and the interval on that increase
only just contains zero, its lower bound being -0.0009. On the point estimate H1's second half holds
at C6, and the reason is the part worth reporting:

| within one model, C6 minus C1 | diff | CI |
|---|---|---|
| 32B | +0.0025 | [-0.0687, +0.0683] |
| 4B | **-0.0595** | **[-0.1169, -0.0037]** |

**The gap widens because the 4B gets WORSE with six frames, not because the 32B gets better.** The
32B is flat, as 11.2 reported. The 4B's decline is the one condition contrast in this study whose
interval excludes zero. So the honest statement of H1 at C6 is not "episode context helps the large
model", it is **"episode context actively harms the small model while leaving the large one
unchanged"**, which widens the gap by damaging the weaker arm.

That has a different consequence for a deployment than the hypothesis implied. The gap is not a
reason to send episodes to the cloud; it is a reason not to send them to the device.

**And on the device the cost runs the same way.** 4B TTFT p50 is 0.9273 s at C6 against 0.2416 s at
C1, so six frames cost the device **3.8 times** a one-frame evaluation and lose 0.06 mAP. For the
device, C6 is worse on both axes at once.

Still outstanding: the 4B's EP-B and EP-G, which are the two conditions where H3's warm-prefix saving
applies, so the episode conditions proper remain 32B-only and section 1's decision rule is still not
applied.
