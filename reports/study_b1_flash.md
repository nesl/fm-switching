# StudyB1-flash — per-question capability of Qwen3-VL 4B and 8B, Instruct and Thinking

**Status: PRE-REGISTERED. Sections 1–5 below were written and committed to disk before any
sweep request was issued.** Results are appended in §6 onward after the run.

**What this study is.** A descriptive capability pass: per-question correctness for
Qwen3-VL-4B and Qwen3-VL-8B, each in Instruct and Thinking mode, on RTV-Bench, OVO-Bench,
HERBench (full) and StreamingBench, at each benchmark's own published query time.

**What this study is not.** It makes **no time-shift, policy, placement or latency claim**.
No latency is measured or reported from this host. 4B and 8B are **not** compared as
small-versus-large; each is a device option, to be compared against 32B later.

**Scoping flag (results consistency check #4/#5).** `research/FORMULATION.md` §Scoping states
"**Single model per deployment.** Every node runs the same model; Q(f, w) does not vary by
node", and scopes per-tier model heterogeneity *to discussion with measurements as evidence*.
This study measures exactly that scoped-out quantity — Q per model. It is therefore recorded
as **capability input for discussion, not as a result bearing on the coupling claim**. Any
later use of these numbers in a policy comparison would require the heterogeneity extension
that §Scoping defers.

---

## 1. Mechanism verification — Step 1: the causal chain

The claim under test: *on identical causal input, model capability and reasoning mode change
per-question correctness.*

The chain, link by link. `research/FORMULATION.md` §State objects defines **Q(f, w)**, the
expected task quality of a fidelity f under workload regime w, as a primitive of the cost
model — the semantic component of Context Inertia, distinct from the physical component. Q is
not an assumed constant: §State objects already records it as measured and workload-dependent
(LoCoMo full 0.34–0.40 vs summary 0.10–0.13). This study holds the *causal input* fixed — the
same frames, rendered by one pinned code path from one pinned decode rule, carrying the same
question and option text at the same query time — and varies only the reader. If per-question
correctness is a property of the reader as well as of the representation, then (a) changing
model capability at fixed input must move per-question correctness, and (b) changing reasoning
mode at fixed input and fixed capability must also move it. If instead correctness at fixed
input is invariant to the reader, then Q(f, w) is a property of the representation alone, a
single Q table serves every tier, and §Scoping's "single model per deployment" simplification
is harmless. The experiment distinguishes these by measuring per-question agreement, not
aggregate accuracy: two arms can post the same accuracy while disagreeing on half the
questions.

The input channel itself is the prerequisite link: if the frames carry no task-relevant
information, every arm is answering from question and option text, and arm differences would
be differences in text priors, not in video understanding. Step 2 and Step 4 test that
prerequisite first.

## 2. Mechanism verification — Step 2: instantiate each link

Pilot: 4B-Instruct, n=60 (30 RTV-Bench + 30 StreamingBench), identical questions across
conditions, run 2026-11-05 19:2x on the 3090 Ti before the sweep.

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| frames carry task-relevant information | accuracy, real frames vs grey frames, same questions | HISTORY 0.533 vs GREY 0.467; guessing floor 0.285 | **YES but WEAK** — +6.7 pp over grey | 24/60 per-question flips HISTORY vs GREY |
| input composition changes correctness | accuracy, RECENT(9) vs HISTORY(37), same questions | 0.667 vs 0.533 | YES, −13.4 pp | 12/60 per-question flips |
| question/option text alone sustains accuracy | grey-frame accuracy vs guessing floor | 0.467 vs 0.285 | **YES — confound present** | grey answer distribution A21/B16/C16/D7, not uniform |
| model capability changes correctness | per-question correctness, 4B vs 8B at fixed input | measured in the sweep | pending | §6 |
| reasoning mode changes correctness | per-question correctness, Instruct vs Thinking at fixed input | measured in the sweep | pending | §6 |

**No link is ABSENT or CONSTANT, so the sweep proceeds.** One link is flagged **WEAK and
confounded**: grey frames score 0.467, which is 18.2 pp above the 0.285 guessing floor and
only 6.7 pp below real 37-frame input. On this subsample most of the headline accuracy is
recoverable from text alone. Consequences, fixed in advance:

1. **Every accuracy in §6 is reported against its grey-frame control, not against the
   guessing floor.** The guessing floor is the wrong reference line for these benchmarks.
2. The grey control is run at the specified 100 requests per arm per input, so each arm has
   its own reference.
3. Arm and capability differences are reported as **per-question agreement** as well as
   accuracy, because an accuracy difference at this margin can be produced by text priors.

## 3. Mechanism verification — Step 3: one representative unit

One request, RTV-Bench `q-group-xxxx`, 4B-Instruct, HISTORY, from the pilot:

```
INPUT
  video            rtv_bench/hf/videos/sports_cam/SportsCam_010.mp4
  query time t     227.67 s          (field: end_time)
  source for t     video_utils.py:177-187 crop_video_ffmpeg -ss 0 -t end_time;
                   infer_model_rtv.py:101,107 passes end_time
  input mode       HISTORY, N=37 targets evenly spaced over [0, 227.67]
  frame selection  latest decoded frame with pts <= target (PyAV)
  max frame pts    227.6604 s   <= t 227.67   ASSERTION HOLDS
  first-frame fb   1  (target 0.0; stream's first pts is 0.033, documented fallback)
  distinct frames  37 of 37
  resize/encode    LANCZOS 768x432, lossless PNG
  prompt tokens    12,580   (37 images + header + question + 3 options + instruction)
  no timestamps or file names appear in the prompt

COST / BUDGETS
  no budget is charged: this study measures no latency and no capacity.
  render 2.50 s and GPU 4.24 s are recorded per request for scheduling only and are
  NOT reported as latency results (host is shared; see "no latency from this host").

DECISION / OUTCOME
  generated tokens 2        finish_reason stop        truncated False
  raw response     'C'
  parser           rtv_extract_pred_letter (prompt_utils.py:16-36)
  pred C   gold C   correct True   unparsed False
```

The arithmetic a reader can check by hand: 37 targets at 227.67/36 = 6.3242 s spacing;
target 36 = 227.67; selected frame pts 227.6604 <= 227.67.

## 4. Mechanism verification — Step 4: negative control

*(Annotation added 2026-11-06, pre-registered text below unaltered: the control as
executed was INVALID — see §7 for the defect and §13 for the corrected control.)*

The mechanism under test is the information channel from video to answer. **Control: replace
every frame with a uniform grey frame of the same size and count, changing nothing else.**

| cell | condition | accuracy | n |
|---|---|---|---|
| 4B-Instruct, HISTORY, RTV+SB pilot | real frames | 0.533 | 60 |
| 4B-Instruct, HISTORY, RTV+SB pilot | grey frames | 0.467 | 60 |
| — | guessing floor | 0.285 | — |

**The control changed the result, so the visual mechanism is operative** — but it moved it by
only 6.7 pp, while the grey condition sits 18.2 pp above the floor. Reported together, as
required. The full grey control (100 requests per arm per input) runs inside the sweep so
every arm in §6 has its own control rather than inheriting this pilot's.

## 5. Mechanism verification — Step 5: alternative explanation

Headline result to be produced: "per-question correctness differs across model capability and
reasoning mode at identical input."

Alternative mechanisms that would produce the same headline:

- **(a) claimed:** the arms differ in how well they read the frames, so correctness differs on
  the questions whose answers are in the frames.
- **(b) text priors:** the arms differ in their question/option text priors, and the frames are
  largely irrelevant. The pilot shows this is a live alternative, not a hypothetical: grey
  frames already deliver 0.467.
- **(c) answer-format compliance:** the arms differ in how reliably they emit a parseable
  option letter, and the parser converts format compliance into apparent accuracy. Thinking,
  with 16,384 max tokens, can truncate before emitting an answer, which the primary metric
  counts as wrong.

**What distinguishes them in the data:** (b) is separated by the per-arm grey control — if an
arm's real-frame minus grey-frame margin is zero, that arm's accuracy is text priors and is
reported as such. (c) is separated by reporting unparsed, empty and truncated counts
*separately* from the primary accuracy, which also counts them wrong, and by the
`pred_strict`/`correct_strict` second parse recorded on every row. If an arm difference
survives neither separation, this experiment cannot attribute it to capability, and the
report says so.

## 5b. Pre-registered stopping and reporting commitments

- Null classification per CLAUDE.md Rule 2 is written into §6 explicitly.
- Coverage is reported per model, arm, input and dataset; any time-boxed stage is reported as
  partial coverage, not as a completed sweep.
- Comparison with published numbers only where model, input and protocol match; otherwise
  stated as not comparable.
- Unparsed/empty/truncated counted wrong in the primary accuracy **and** reported separately.

---

## 6. Run outcome and coverage

Both GPUs ran unattended from 19:37 on 2026-11-05 and stopped taking new requests at the
pre-registered 09:00 cutoff on 2026-11-06. Neither stop rule fired: free disk on `/mnt/ssd`
never fell below 1,801 GB (threshold 50 GB), and the per-arm failure rate was 2 in ~20,000
(threshold 1%). No job this run did not start was interrupted; the A6000 was held until
another user's CarlaUE4 job finished at 19:33 (see §9).

Rows written: **40,080** total = 39,276 benchmark + 800 grey control + 4 render errors.

### 6.1 Coverage (fraction of eligible questions evaluated)

| dataset | input | 4B-Instruct | 4B-Thinking | 8B-Instruct | 8B-Thinking | eligible |
|---|---|---|---|---|---|---|
| rtv_bench | RECENT | 100.0% (4,608) | 4.3% (200) | 100.0% (4,608) | 4.3% (200) | 4,608 |
| rtv_bench | HISTORY | 80.6% (3,712) | 4.3% (200) | 91.7% (4,224) | 4.3% (200) | 4,608 |
| ovo_bench | RECENT | 100.0% (3,035) | 13.2% (400) | 100.0% (3,035) | 13.2% (400) | 3,035 |
| ovo_bench | HISTORY | 100.0% (3,035) | 13.2% (400) | 100.0% (3,035) | 13.2% (400) | 3,035 |
| streaming_bench | RECENT | 99.9% (3,248) | 6.2% (200) | 99.9% (3,248) | 6.2% (200) | 3,250 |
| streaming_bench | HISTORY | — | 6.2% (200) | — | 6.2% (200) | 3,250 |
| herbench | HISTORY | — | 0.4% (96) | — | 0.7% (192) | 27,566 |

Coverage is highly uneven **by design**: stage 1 ran Instruct to exhaustion in a fixed
order and handed off to stage 2 at 05:00 wherever it had reached; stage 2 then sampled
Thinking in 200-question batches alternating across the five sets. Consequences:

- **Complete cells (100%):** Instruct RECENT on RTV-Bench, OVO-Bench and StreamingBench,
  and Instruct HISTORY on OVO-Bench, for both models. These are the only cells where an
  accuracy is a dataset-level accuracy rather than a sample.
- **Partial by time-box:** Instruct HISTORY on RTV-Bench (80.6% on 4B, 91.7% on 8B).
- **Not reached at all:** Instruct HISTORY on StreamingBench, and all Instruct on HERBench.
- **Thinking is a small stratified sample everywhere** (4.3%–13.2%; HERBench 0.4%–0.7%).
  Because the order is a fixed seed-0 round robin stratified by task, each sample is a
  valid sample of its dataset, but the n is small and the intervals below are wide.
- **HERBench is 0.4%–0.7% covered.** It is 27,566 of the 38,459 eligible questions — 72% of
  the study's question pool — and it is effectively absent from this run. Its numbers below
  rest on 96 (4B) and 192 (8B) questions and should not be read as HERBench results.

At the measured HISTORY throughput (~0.3 req/s, 37 images ≈ 12.6k prompt tokens) a single
full pass of HERBench HISTORY is ~25 GPU-hours per arm; it was not reachable in one night
and no amount of scheduling inside the 13.5-hour window would have reached it.

### 6.2 Questions that could not be evaluated

| model | input | qid | cause |
|---|---|---|---|
| 4B | RECENT | `Real-Time Visual Understanding_sample_332_5` | render: InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()' |
| 4B | RECENT | `Real-Time Visual Understanding_sample_332_4` | render: InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()' |
| 8B | RECENT | `Real-Time Visual Understanding_sample_332_5` | render: InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()' |
| 8B | RECENT | `Real-Time Visual Understanding_sample_332_4` | render: InvalidDataError: [Errno 1094995529] Invalid data found when processing input: 'avcodec_send_packet()' |

Both models failed the same two StreamingBench questions on the same video
(`Real-Time Visual Understanding/sample_332`) with an identical PyAV decode error, so this
is a corrupt source file, not a run fault. These rows never reached the model, so they are
counted as **coverage loss, not as wrong answers**: scoring an unaskable question as wrong
would push the accuracy down for a reason that has nothing to do with the model.

Primary accuracy demoted **2** rows that the upstream parser scored correct but whose
response was truncated at the 16,384-token limit (`finish_reason=length`). Per the
pre-registration these count as wrong in the primary accuracy; the parser's own verdict is
kept in `accuracy_lenient` in `analysis.json` so the two never diverge silently.

## 7. The negative control did not test what it was supposed to test

> ### INVALID — grey-frame negative control of the 2026-11-05/06 run (notice added 2026-11-06)
>
> **The grey-frame control reported in §7 is INVALID and is superseded by §13.** It is not a
> measurement of accuracy-without-video and must not be cited as one, as a floor, or as a
> reference line for any §8 accuracy.
>
> **Defect, in code:** `experiments/benchmarks/b1_run.py:428-431` hardcodes a single synthetic
> question (`"What is shown?"`, options `one/two/three/four`, `gold` fixed to `"A"`) that is
> drawn from no dataset, and `b1_run.py:433` submits *that same row object* 100 times, varying
> only `gidx`, which `b1_run.py:335` uses in the dedup key alone. The frame side was correct
> (`b1_run.py:242-248` produces the right frame count, 768x432, lossless PNG, same template).
>
> **Three consequences, each verified in the written rows:**
> 1. All 100 requests in every cell share **1 distinct `prompt_sha256`** — byte-identical prompts.
> 2. Under greedy Instruct decoding that yields **1 distinct response** per cell, so n=100 carries
>    the information of n=1. The Instruct cells' `1.000` is one deterministic answer, not a rate.
> 3. `gold` is constant `"A"`, so the statistic computed is P(model emits "A"), i.e. an
>    answer-position bias, not P(correct without visual information).
>
> **Affected files (kept, not deleted, not modified):** the 400 rows with `grey=true` in each of
> `results/benchmarks/study_b1_flash/model_4B/requests.part000.jsonl.gz` and `model_8B/...`, and
> the `grey` block of `results/benchmarks/study_b1_flash/analysis.json`.
> **Not affected:** every real benchmark row. Grey rows are keyed separately (`b1_run.py:335`) and
> excluded from all real-arm statistics, so correcting the control changes no real arm.


**This section is a defect report on this run, not a result.**

§4 pre-registered a grey-frame control: identical prompts with featureless grey images, to
establish how much of the measured accuracy survives with no visual information. The runner
implemented it as **one synthetic question** — "What is shown?", options one/two/three/four,
gold always `A` — repeated 100 times per arm per input, instead of real benchmark questions
paired with grey frames. What that measures:

| model | arm | input | n | "accuracy" | prediction distribution |
|---|---|---|---|---|---|
| 4B | Instruct | HISTORY | 100 | 1.000 | {'A': 100} |
| 4B | Instruct | RECENT | 100 | 1.000 | {'A': 100} |
| 4B | Thinking | HISTORY | 100 | 1.000 | {'A': 100} |
| 4B | Thinking | RECENT | 100 | 1.000 | {'A': 100} |
| 8B | Instruct | HISTORY | 100 | 1.000 | {'A': 100} |
| 8B | Instruct | RECENT | 100 | 1.000 | {'A': 100} |
| 8B | Thinking | HISTORY | 100 | 0.610 | {'A': 61, 'B': 17, 'C': 22} |
| 8B | Thinking | RECENT | 100 | 1.000 | {'A': 100} |

Seven of the eight cells answer `A` 100 times out of 100 and therefore score 1.000 against
a gold that is always `A`. This is an answer-position bias on a featureless image, measured
against a constant gold. It is **uninformative about the quantity the control exists to
measure** and it cannot be used as the reference line for any accuracy in §8.

This is the failure mode CLAUDE.md Step 4 is written to catch: a control that returns a
clean, extreme number for a reason unrelated to the mechanism. A control that scores 1.000
is not a strong result; here it is the signature of a degenerate design.

The one cell that is not saturated is informative about something else: 8B-Thinking/HISTORY
answers A:61 / B:17 / C:22, i.e. extended generation on featureless input partially breaks
the position bias that the Instruct arms show absolutely.

The pilot recorded in §2 used the correct construction (real questions, grey frames) and
gave 0.467 against a 0.285 guessing floor and 0.533 for real 37-frame input — i.e. roughly
three-quarters of apparent accuracy surviving with no video. **That pilot figure is n=60 on
4B-Instruct only and is not a substitute for the control on this run's 39,276 rows.**

Consequence, stated before any interpretation: the fraction of §8's accuracy attributable
to the visual channel is **unmeasured in this run**. Per CLAUDE.md Step 4 and Rule 1, the
nulls in §8.2 are therefore **not settled findings**. Re-running the control correctly costs
~800 requests (~40 min on both GPUs) and needs no re-inference of the benchmark rows.

## 8. Observations

Primary accuracy counts unparsed, empty and truncated as wrong. Intervals are 95% bootstrap
(2,000 resamples, seed 0) **resampling videos, not questions**, because questions sharing a
video share frames and are not independent. Guessing floor is the mean of 1/(number of
options) over the questions in the cell.

### 8.1 Accuracy by dataset, input, model and arm

| dataset | input | model | arm | n | cov | floor | accuracy | 95% CI | trunc | unparsed | gen tok p50/p90/max |
|---|---|---|---|---|---|---|---|---|---|---|---|
| herbench | HISTORY | 4B | Thinking | 96 | 0.4% | 0.200 | **0.396** | [0.305, 0.484] | 0.000 | 0.000 | 1802/5295/9265 |
| herbench | HISTORY | 8B | Thinking | 192 | 0.7% | 0.200 | **0.479** | [0.396, 0.562] | 0.000 | 0.000 | 976/3258/9798 |
| ovo_bench | HISTORY | 4B | Instruct | 3,035 | 100.0% | 0.349 | **0.567** | [0.539, 0.596] | 0.000 | 0.000 | 2/2/3 |
| ovo_bench | HISTORY | 4B | Thinking | 400 | 13.2% | 0.354 | **0.507** | [0.459, 0.555] | 0.003 | 0.000 | 359/2443/16384 |
| ovo_bench | HISTORY | 8B | Instruct | 3,035 | 100.0% | 0.349 | **0.584** | [0.554, 0.613] | 0.000 | 0.000 | 2/2/6 |
| ovo_bench | HISTORY | 8B | Thinking | 400 | 13.2% | 0.354 | **0.568** | [0.518, 0.621] | 0.000 | 0.003 | 211/1723/10174 |
| ovo_bench | RECENT | 4B | Instruct | 3,035 | 100.0% | 0.349 | **0.543** | [0.510, 0.578] | 0.000 | 0.000 | 2/2/3 |
| ovo_bench | RECENT | 4B | Thinking | 400 | 13.2% | 0.354 | **0.552** | [0.498, 0.614] | 0.003 | 0.000 | 265/1236/16384 |
| ovo_bench | RECENT | 8B | Instruct | 3,035 | 100.0% | 0.349 | **0.552** | [0.518, 0.586] | 0.000 | 0.000 | 2/2/60 |
| ovo_bench | RECENT | 8B | Thinking | 400 | 13.2% | 0.354 | **0.593** | [0.542, 0.645] | 0.000 | 0.000 | 199/950/4590 |
| rtv_bench | HISTORY | 4B | Instruct | 3,712 | 80.6% | 0.300 | **0.587** | [0.570, 0.604] | 0.000 | 0.000 | 2/2/2 |
| rtv_bench | HISTORY | 4B | Thinking | 200 | 4.3% | 0.307 | **0.570** | [0.503, 0.640] | 0.010 | 0.010 | 430/2145/16384 |
| rtv_bench | HISTORY | 8B | Instruct | 4,224 | 91.7% | 0.301 | **0.568** | [0.552, 0.583] | 0.000 | 0.000 | 2/2/2 |
| rtv_bench | HISTORY | 8B | Thinking | 200 | 4.3% | 0.307 | **0.525** | [0.459, 0.599] | 0.000 | 0.000 | 245/1221/6163 |
| rtv_bench | RECENT | 4B | Instruct | 4,608 | 100.0% | 0.304 | **0.655** | [0.640, 0.671] | 0.000 | 0.000 | 2/2/2 |
| rtv_bench | RECENT | 4B | Thinking | 200 | 4.3% | 0.307 | **0.640** | [0.573, 0.707] | 0.000 | 0.000 | 251/1673/6046 |
| rtv_bench | RECENT | 8B | Instruct | 4,608 | 100.0% | 0.304 | **0.670** | [0.654, 0.684] | 0.000 | 0.000 | 2/2/2 |
| rtv_bench | RECENT | 8B | Thinking | 200 | 4.3% | 0.307 | **0.670** | [0.607, 0.732] | 0.000 | 0.000 | 181/1118/3705 |
| streaming_bench | HISTORY | 4B | Thinking | 200 | 6.2% | 0.250 | **0.675** | [0.608, 0.741] | 0.000 | 0.000 | 400/2980/8342 |
| streaming_bench | HISTORY | 8B | Thinking | 200 | 6.2% | 0.250 | **0.655** | [0.590, 0.721] | 0.000 | 0.000 | 198/2244/5202 |
| streaming_bench | RECENT | 4B | Instruct | 3,248 | 99.9% | 0.250 | **0.759** | [0.739, 0.777] | 0.000 | 0.000 | 2/2/2 |
| streaming_bench | RECENT | 4B | Thinking | 200 | 6.2% | 0.250 | **0.705** | [0.638, 0.768] | 0.000 | 0.000 | 308/1723/6256 |
| streaming_bench | RECENT | 8B | Instruct | 3,248 | 99.9% | 0.250 | **0.763** | [0.745, 0.782] | 0.002 | 0.002 | 2/2/64 |
| streaming_bench | RECENT | 8B | Thinking | 200 | 6.2% | 0.250 | **0.700** | [0.627, 0.770] | 0.000 | 0.000 | 219/1452/3359 |

Observations, without interpretation:

- Every cell is above its guessing floor, by 20–51 points.
- Truncation is ≤1.0% everywhere and 0.000 in every Instruct cell; unparsed is ≤1.0%
  everywhere. Neither is large enough to move any accuracy above by more than a point.
- Instruct emits 2 generated tokens at p50 in every cell (one letter plus stop). Thinking
  emits 181–1,802 at p50 and up to 5,295 at max, i.e. two to three orders of magnitude more.
- Per-task breakdowns for all 412 cells are in `analysis.json`; they are not reproduced here
  because most per-task Thinking cells have n < 30.

### 8.2 Thinking − Instruct on matched questions

Matched means the same qid, same input, same model, both arms. Bootstrap by video.

| model | dataset | input | n matched | acc Thinking | acc Instruct | diff | 95% CI | per-question flip rate |
|---|---|---|---|---|---|---|---|---|
| 4B | ovo_bench | HISTORY | 400 | 0.507 | 0.545 | -0.037 | [-0.088, +0.016] | 0.282 |
| 4B | ovo_bench | RECENT | 400 | 0.552 | 0.547 | +0.005 | [-0.036, +0.046] | 0.180 |
| 4B | rtv_bench | HISTORY | 200 | 0.570 | 0.555 | +0.015 | [-0.050, +0.083] | 0.235 |
| 4B | rtv_bench | RECENT | 200 | 0.640 | 0.665 | -0.025 | [-0.084, +0.038] | 0.185 |
| 4B | streaming_bench | RECENT | 200 | 0.705 | 0.700 | +0.005 | [-0.046, +0.059] | 0.135 |
| 8B | ovo_bench | HISTORY | 400 | 0.568 | 0.557 | +0.010 | [-0.037, +0.055] | 0.225 |
| 8B | ovo_bench | RECENT | 400 | 0.593 | 0.560 | +0.033 | [-0.011, +0.073] | 0.198 |
| 8B | rtv_bench | HISTORY | 200 | 0.525 | 0.580 | -0.055 | [-0.116, +0.005] | 0.185 |
| 8B | rtv_bench | RECENT | 200 | 0.670 | 0.690 | -0.020 | [-0.066, +0.030] | 0.130 |
| 8B | streaming_bench | RECENT | 200 | 0.700 | 0.700 | +0.000 | [-0.053, +0.052] | 0.160 |

- **All ten confidence intervals contain zero.** The largest point difference is -0.055
  (8B, RTV, HISTORY) and the largest in Thinking's favour is +0.033 (8B, OVO, RECENT).
- **Per-question correctness changes substantially anyway: 13.0%–29.0% of matched questions
  flip** between arms. Aggregate accuracy is near-identical while the identity of the
  questions answered correctly is not.

### 8.3 HISTORY − RECENT on matched questions

Labelled as a comparison of **inputs at different frame counts** (37 vs 9), not as a
time-shift or a context-length result. Token counts reported alongside.

| model | dataset | arm | n matched | acc HISTORY | acc RECENT | diff | 95% CI | flip rate | gen tok p50 H/R |
|---|---|---|---|---|---|---|---|---|---|
| 4B | ovo_bench | Instruct | 3,035 | 0.567 | 0.543 | +0.024 | [+0.002, +0.046] | 0.237 | 2/2 |
| 4B | ovo_bench | Thinking | 400 | 0.507 | 0.552 | -0.045 | [-0.099, +0.010] | 0.290 | 359/265 |
| 4B | rtv_bench | Instruct | 3,712 | 0.587 | 0.650 | -0.063 | [-0.077, -0.049] | 0.208 | 2/2 |
| 4B | rtv_bench | Thinking | 200 | 0.570 | 0.640 | -0.070 | [-0.142, +0.000] | 0.250 | 430/251 |
| 4B | streaming_bench | Thinking | 200 | 0.675 | 0.705 | -0.030 | [-0.094, +0.036] | 0.230 | 400/308 |
| 8B | ovo_bench | Instruct | 3,035 | 0.584 | 0.552 | +0.033 | [+0.009, +0.056] | 0.255 | 2/2 |
| 8B | ovo_bench | Thinking | 400 | 0.568 | 0.593 | -0.025 | [-0.079, +0.029] | 0.285 | 211/199 |
| 8B | rtv_bench | Instruct | 4,224 | 0.568 | 0.668 | -0.100 | [-0.114, -0.086] | 0.220 | 2/2 |
| 8B | rtv_bench | Thinking | 200 | 0.525 | 0.670 | -0.145 | [-0.211, -0.077] | 0.265 | 245/181 |
| 8B | streaming_bench | Thinking | 200 | 0.655 | 0.700 | -0.045 | [-0.113, +0.020] | 0.235 | 198/219 |

- On **RTV-Bench, 37 frames scores lower than 9 frames**, and these are the two largest and
  only fully-powered contrasts in the table: 4B Instruct -0.063 [-0.077, -0.049] on n=3,712
  and 8B Instruct -0.100 [-0.114, -0.086] on n=4,224. Both intervals exclude zero.
- On **OVO-Bench the sign reverses** for Instruct: +0.024 [+0.002, +0.046] (4B) and
  +0.033 [+0.009, +0.056] (8B), both just excluding zero on complete coverage.
- Every Thinking contrast has a CI containing zero except 8B/RTV (-0.145 [-0.211, -0.077]).
- Flip rates are 20.8%–29.0%, again larger than any accuracy difference.
- Prompt tokens: RECENT p50 3,109; HISTORY p50 12,587.


## 9. Environment, stack difference, and GPU conflict

| item | this run (flash) | D-series reference | matches? |
|---|---|---|---|
| vLLM | **0.19.1** | 0.31.0 | **no** |
| torch | **2.10.0+cu128** | 2.13.0+cu129 | **no** |
| GPU | RTX 3090 Ti (sm_86) / RTX A6000 (sm_86) | H100 NVL (sm_90) | no |
| attention backend | FlashAttention-2 (sm_86 has no FA-3) | FlashAttention-3 | **no** |
| model repos + revisions | 4 pinned SHAs (below) | same | yes |
| dtype / seed | bfloat16 / 0 | bfloat16 / 0 | yes |
| prefix caching | off (`--no-enable-prefix-caching`) | off | yes |
| mm processor cache | off (`--mm-processor-cache-gb 0`) | off | yes |
| decoding, Instruct | greedy, max_tokens 64, logprobs 20 | same | yes |
| decoding, Thinking | T=1.0, top_p 0.95, top_k 20, max_tokens 16384, seed 0 | same | yes |
| concurrency | 8 per GPU | 8 | yes |

The stack difference is **not a choice**: flash's driver is 550.163.01, which supports CUDA
12.x only, and every vLLM release on PyPI from 0.20.0 onward is a CUDA-13 build
(`humming-kernels[cu13]`, `nvidia-cutlass-dsl[cu13]`). 0.19.1 is the newest CUDA-12 release.
Raising the driver needs sudo and a reboot on a shared host. Any comparison of these numbers
with H100 numbers from the D-series stack is therefore **a comparison across two different
inference stacks and two different attention backends**, and per CLAUDE.md must say so.

Model revisions (all pre-cached under `/mnt/ssd/hf_models`, no downloads this run):

| arm | repo | revision |
|---|---|---|
| 4B-Instruct | Qwen/Qwen3-VL-4B-Instruct | `ebb281ec70b05090aa6165b016eac8ec08e71b17` |
| 4B-Thinking | Qwen/Qwen3-VL-4B-Thinking | `1de27d8c51f12e819435303b9e84c4e25ba8401e` |
| 8B-Instruct | Qwen/Qwen3-VL-8B-Instruct | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` |
| 8B-Thinking | Qwen/Qwen3-VL-8B-Thinking | `92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b` |

Frame rendering, shared with the planned H100 run:

- `experiments/benchmarks/b1_frames.py`, SHA-256 `16d37b520dc102b6605033b361b2aaba46b0621fc3a5056c91b76f3c126e2b7a`
- `experiments/benchmarks/b1_parse.py`, SHA-256 `1487345ef6883e1b86560d85d02f5307205243be519eb687d8c958bb94b1c0f4`
- prompt template set, SHA-256 `25a230fd94807c6c11eded1b4c0e481dee87e66eed0597e72b19fd864e1e0274`
- PyAV 17.1.0; libavcodec 62.28.101, libavformat 62.12.101, libavutil 60.26.101; Pillow 12.3.0
- a SHA-256 is recorded for every rendered frame on every row, so frame identity is directly
  comparable with the H100 run without storing any frame.

**GPU conflict.** GPU 1 (A6000) was held by another user's CarlaUE4 job (5 processes, 4,554 MiB,
100% utilisation) when this task began. Per the instruction not to interrupt jobs this run did
not start, 8B was not launched until that job exited at ~19:33; both arms then started at 19:37.
No other foreign process appeared on either GPU for the rest of the run (watchdog logged
`foreign=[]` every 120 s). The 8B run therefore lost no time relative to 4B.

**Data path.** The task specified `/mnt/ssd/datasets`; actual path is
`/mnt/ssd/hf_models/datasets`, because `/mnt/ssd` is owned by `ziqi:root` and is not writable
by this user. Same filesystem, same contents.

## 10. Results consistency check

| # | check | outcome |
|---|---|---|
| 1 | cross-check vs committed measurements | **no valid prior exists.** The only prior Instruct-vs-Thinking vision accuracy is StudyD/StudyD2, both marked INVALID in `research/EXPERIMENTS.md`; per CLAUDE.md these must not be cited or recomputed from. No prior committed value for any of these four benchmarks. Nothing to cross-check against, and nothing suppressed. |
| 2 | physical plausibility | PASS. 12,587-token HISTORY prompts at ~0.31 req/s ≈ 3,900 prompt tok/s on a 3090 Ti; 3,109-token RECENT at ~1.57 req/s ≈ 4,880 tok/s. Both below the committed A6000 cold-prefill ~7,100 tok/s, as expected for a smaller card with vision-encoder work on top. No measurement implies a rate faster than the committed curves, so no caching artifact. Prefix and mm caches were off and `--no-enable-prefix-caching` is recorded in `run_meta.json`. |
| 3 | distribution sanity | PASS with one note. Accuracies vary across tasks and datasets (0.396–0.763) and no two cells agree to three decimals. Generated-token p50 is exactly 2 in every Instruct cell — this is **not** short-circuiting: greedy Instruct emits one option letter plus a stop token, which is 2 tokens by construction, and max is also 2. The grey control's 1.000 constants are the degenerate control of §7, not a distribution artifact. |
| 4 | definition audit | PASS. RECENT = 9 frames over [t−3, t]; HISTORY = 37 frames over [0, t], whole video for HERBench. Both are defined in this study for the first time; no prior committed experiment uses these names, so there is no name reused with two definitions. "Query time" is taken from a cited upstream field per dataset (`end_time` for RTV, `realtime`/per-sub-query for OVO, `time_stamp` for StreamingBench, none for HERBench) and recorded per row as `t_query_s` with `t_field`. |
| 5 | claim linkage | **FLAGGED.** These measurements instantiate `Q(f, w)` from FORMULATION §State objects. But FORMULATION §Scoping states "Single model per deployment. Every node runs the same model; Q(f, w) does not vary by node", and admits such measurements only "to discussion with those measurements as evidence". StudyB1-flash is therefore recorded as **capability input for discussion, not as evidence on the representation/placement coupling claim**, and must not be cited as a gate result. |
| 6 | proxy validity | PASS, with the §7 defect separate. Frames are selected by decode timestamp (`frame.pts * time_base`), not by a frame-index proxy, and a hard assertion on every row guarantees no frame has pts greater than the query time. Grey-frame accuracy was intended as the proxy for "accuracy available without the visual channel"; as built it measures answer-position bias instead, and is **not** used for any conclusion (§7). |

## 11. Interpretation, separated from the observations above

The pre-registered causal claim was: *on identical causal input, model capability and reasoning
mode change per-question correctness.*

**What the run supports.** Per-question correctness does change, and substantially. Switching
Instruct→Thinking at fixed model, dataset and input flips 13.0%–29.0% of matched questions;
switching RECENT→HISTORY at fixed model and arm flips 20.8%–29.0%. These flip rates are five to
ten times larger than any accuracy difference in the same cells. On the measured datasets, arm
and input visibly reorganise *which* questions are answered correctly.

**What the run does not support.** Aggregate accuracy does not distinguish the arms. All ten
Thinking−Instruct intervals contain zero, on matched questions with video-clustered bootstrap.
Thinking spends 90×–900× more generated tokens for no detectable accuracy gain on these four
benchmarks at these two sizes.

**Null classification (CLAUDE.md Rule 2).** The Thinking−Instruct accuracy null is
**INCONCLUSIVE, not a real negative.** Two reasons, both design faults of this run and not
properties of the models:

1. The negative control was degenerate (§7), so the fraction of accuracy carried by the visual
   channel is unmeasured. The §2 pilot suggests text priors may carry roughly three-quarters of
   it. If that holds at scale, the arms are being compared on a channel worth a few points, and
   an interval containing zero is the expected outcome whether or not reasoning mode matters.
2. Every Thinking cell is a 4.3%–13.2% sample (n=96–400). The intervals are 8–16 points wide,
   which does not exclude differences the study would care about.

Calling this a settled negative would repeat the E36/E36b/E36c failure that CLAUDE.md cites:
a null produced by a mechanism that was never properly exercised.

The HISTORY−RECENT contrast on RTV-Bench is on firmer ground — complete or near-complete
coverage, n=3,712 and n=4,224, intervals excluding zero — and the direction is that **more
frames scored lower**. The sign reverses on OVO-Bench. This is reported as a descriptive
property of these two input constructions on these two datasets. It is not evidence about
context length, about time-shifting, or about any policy, and no threshold was fitted to it.

**What is explicitly not claimed.** No latency or throughput number from this host is offered
as a performance result (the request rates in check 2 exist only to validate plausibility).
4B and 8B are not compared as small-versus-large; each is a device option to be compared with
32B later. No comparison with published benchmark numbers is made: the frame-selection
protocol, resolution, frame count and prompt template here match no published setup, so those
numbers are **not comparable**.

## 12. Limitations

- HERBench, 72% of the question pool, is 0.4%–0.7% covered. The study has essentially not
  measured it.
- Instruct HISTORY on StreamingBench was never reached.
- The negative control must be re-run before any §8.2 null is treated as a finding (§7).
- Inference stack differs from the D-series reference in vLLM, torch and attention backend (§9).
- StreamingBench excludes 1,300 questions by upstream definition, listed in
  `index/index_summary.json`: Omni_Source_Understanding (1,000; requires audio) and
  Proactive_Output + Proactive_Output_50 (300; upstream scoring cannot be applied unchanged and
  requires video after the query time).
- HERBench Lite-v2 lists 1,971 unique question_ids of which only 1,429 appear in
  `herbench_annotations.json`; 542 are absent upstream (e.g. `ASII_17250`) and are not evaluated.
- 65 HERBench questions were dropped for one absent upstream video.

---

## 13. Scope changes (user decisions, 2026-11-06)

Recorded as decisions, not as findings. These change what StudyB1 covers; they do not change
any measurement already taken.

1. **HERBench is removed from StudyB1.** Its partial rows (96 on 4B, 192 on 8B, all
   Thinking/HISTORY, 0.4%–0.7% coverage) are **kept on disk and excluded from every B1
   analysis**, and are labelled as excluded wherever they appear. They are not deleted and not
   reported as HERBench results. The §8.1 HERBench rows above predate this decision and are
   superseded by §15, which omits HERBench.
2. **The StreamingBench Instruct HISTORY remainder is not run.** Coverage stays as measured:
   0 of 3,250 for Instruct/HISTORY, reported as is rather than back-filled.
3. **Thinking stays at its current sample** (4.3%–13.2% per dataset). Every Thinking comparison
   uses **only matched questions and matched inputs**, so no Thinking number is compared against
   a differently-sampled Instruct number.

Consequence for the question pool: StudyB1 now covers RTV-Bench (4,608), OVO-Bench (3,035) and
StreamingBench (3,250) — 10,893 questions per input per arm, with HERBench's 27,566 out of scope.

---

## 14. Corrected grey-frame control (StudyB1-grey2)

Supersedes the INVALID control of §7. One defect was fixed and nothing else: each grey
request now carries a **real question with its option text verbatim from the annotation**,
and only the pixel content is replaced by uniform grey (128,128,128).

Everything else is held identical to the real arm, verified before the run:

| property | real request | grey request |
|---|---|---|
| prompt text (header, question, options, instruction) | — | **identical** |
| image count | 9 (RECENT) / 37 (HISTORY) | 9 / 37 |
| resolution | 768x432 | 768x432 |
| encoding | lossless PNG, RGB | lossless PNG, RGB |
| template SHA-256 | `25a230fd…` | `25a230fd…` |
| decoding | per arm | same per arm (Thinking: T=1.0, top_p 0.95, top_k 20, max 16384, seed 0) |

100 grey requests per model, arm, input and dataset that has real results. One shared
question set per (dataset, input), drawn seed-0 from the qids common to every cell with real
results there, so the control is matched across models and arms. HERBench is out of scope (§13).

Three reference lines are reported beside the grey accuracy, because a grey score can be
inflated by label skew rather than by text priors:

- **guessing floor** — mean of 1/(number of options) over the question set
- **majority-letter baseline** — always answer the most frequent gold letter in that set
- **always-A baseline** — always answer A (the statistic the invalid control accidentally measured)

| dataset | input | model | arm | n | grey acc | 95% CI | floor | majority | always-A | distinct prompts | pred distribution |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ovo_bench | HISTORY | 4B | Instruct | 100 | **0.350** | [0.260, 0.442] | 0.347 | 0.190 | 0.140 | 94 | No:30, 0:20, A:17, D:11, B:11, C:11 |
| ovo_bench | HISTORY | 4B | Thinking | 100 | **0.360** | [0.270, 0.456] | 0.347 | 0.190 | 0.140 | 94 | No:30, 0:20, B:16, D:14, C:10, A:10 |
| ovo_bench | HISTORY | 8B | Instruct | 100 | **0.390** | [0.296, 0.490] | 0.347 | 0.190 | 0.140 | 94 | No:29, 0:20, B:18, D:14, C:9, A:9 |
| ovo_bench | HISTORY | 8B | Thinking | 100 | **0.370** | [0.274, 0.464] | 0.347 | 0.190 | 0.140 | 94 | No:29, 0:20, D:16, B:15, C:10, A:9 |
| ovo_bench | RECENT | 4B | Instruct | 100 | **0.350** | [0.260, 0.441] | 0.347 | 0.190 | 0.140 | 94 | No:30, 0:20, A:19, B:12, C:11, D:8 |
| ovo_bench | RECENT | 4B | Thinking | 100 | **0.340** | [0.250, 0.436] | 0.347 | 0.190 | 0.140 | 94 | No:30, 0:20, B:16, A:12, D:11, C:11 |
| ovo_bench | RECENT | 8B | Instruct | 100 | **0.370** | [0.277, 0.465] | 0.347 | 0.190 | 0.140 | 94 | No:30, 0:20, B:16, D:14, A:13, C:6 |
| ovo_bench | RECENT | 8B | Thinking | 100 | **0.360** | [0.272, 0.456] | 0.347 | 0.190 | 0.140 | 94 | No:30, 0:20, D:15, B:14, C:13, A:8 |
| rtv_bench | HISTORY | 4B | Instruct | 100 | **0.330** | [0.237, 0.424] | 0.307 | 0.400 | 0.400 | 99 | A:46, B:27, C:18, D:9 |
| rtv_bench | HISTORY | 4B | Thinking | 100 | **0.260** | [0.176, 0.351] | 0.307 | 0.400 | 0.400 | 99 | B:45, A:28, D:15, C:12 |
| rtv_bench | HISTORY | 8B | Instruct | 100 | **0.270** | [0.184, 0.362] | 0.307 | 0.400 | 0.400 | 99 | B:39, A:30, C:19, D:12 |
| rtv_bench | HISTORY | 8B | Thinking | 100 | **0.320** | [0.226, 0.417] | 0.307 | 0.400 | 0.400 | 99 | B:41, A:28, D:17, C:14 |
| rtv_bench | RECENT | 4B | Instruct | 100 | **0.360** | [0.262, 0.455] | 0.307 | 0.400 | 0.400 | 99 | A:49, B:29, D:11, C:11 |
| rtv_bench | RECENT | 4B | Thinking | 100 | **0.220** | [0.144, 0.306] | 0.307 | 0.400 | 0.400 | 99 | B:50, A:25, D:12, C:12, __UNPARSED__:1 |
| rtv_bench | RECENT | 8B | Instruct | 100 | **0.290** | [0.200, 0.380] | 0.307 | 0.400 | 0.400 | 99 | A:35, B:34, C:17, D:14 |
| rtv_bench | RECENT | 8B | Thinking | 100 | **0.330** | [0.233, 0.429] | 0.307 | 0.400 | 0.400 | 99 | B:41, A:25, C:18, D:16 |
| streaming_bench | HISTORY | 4B | Thinking | 100 | **0.390** | [0.294, 0.490] | 0.250 | 0.290 | 0.240 | 99 | B:36, D:25, C:25, A:14 |
| streaming_bench | HISTORY | 8B | Thinking | 100 | **0.510** | [0.414, 0.604] | 0.250 | 0.290 | 0.240 | 99 | D:30, B:28, C:23, A:19 |
| streaming_bench | RECENT | 4B | Instruct | 100 | **0.440** | [0.343, 0.539] | 0.250 | 0.290 | 0.240 | 99 | A:36, C:33, D:18, B:13 |
| streaming_bench | RECENT | 4B | Thinking | 100 | **0.440** | [0.343, 0.536] | 0.250 | 0.290 | 0.240 | 99 | B:32, C:28, D:23, A:17 |
| streaming_bench | RECENT | 8B | Instruct | 100 | **0.380** | [0.286, 0.476] | 0.250 | 0.290 | 0.240 | 99 | D:27, B:25, A:23, C:23, __UNPARSED__:2 |
| streaming_bench | RECENT | 8B | Thinking | 100 | **0.510** | [0.412, 0.606] | 0.250 | 0.290 | 0.240 | 99 | B:32, D:27, C:26, A:15 |

The `distinct prompts` column is the direct check that the §7 defect is gone: it equals the
number of requests in the cell, where the invalid control had 1.

## 15. Accuracy with the grey reference beside it (HERBench excluded)

Primary accuracy counts unparsed, empty and truncated as wrong. Intervals are 95% bootstrap
(2,000 resamples, seed 0) resampling **videos**. `acc − grey` is the accuracy above the
same cell's corrected grey control; it is an estimate with no test attached.

| dataset | input | model | arm | n | cov | floor | grey | accuracy | 95% CI | acc − grey | trunc | unparsed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ovo_bench | HISTORY | 4B | Instruct | 3,035 | 100.0% | 0.349 | 0.350 | **0.567** | [0.539, 0.596] | +0.217 | 0.000 | 0.000 |
| ovo_bench | HISTORY | 4B | Thinking | 400 | 13.2% | 0.354 | 0.360 | **0.507** | [0.459, 0.555] | +0.147 | 0.003 | 0.000 |
| ovo_bench | HISTORY | 8B | Instruct | 3,035 | 100.0% | 0.349 | 0.390 | **0.584** | [0.554, 0.613] | +0.194 | 0.000 | 0.000 |
| ovo_bench | HISTORY | 8B | Thinking | 400 | 13.2% | 0.354 | 0.370 | **0.568** | [0.518, 0.621] | +0.198 | 0.000 | 0.003 |
| ovo_bench | RECENT | 4B | Instruct | 3,035 | 100.0% | 0.349 | 0.350 | **0.543** | [0.510, 0.578] | +0.193 | 0.000 | 0.000 |
| ovo_bench | RECENT | 4B | Thinking | 400 | 13.2% | 0.354 | 0.340 | **0.552** | [0.498, 0.614] | +0.212 | 0.003 | 0.000 |
| ovo_bench | RECENT | 8B | Instruct | 3,035 | 100.0% | 0.349 | 0.370 | **0.552** | [0.518, 0.586] | +0.182 | 0.000 | 0.000 |
| ovo_bench | RECENT | 8B | Thinking | 400 | 13.2% | 0.354 | 0.360 | **0.593** | [0.542, 0.645] | +0.233 | 0.000 | 0.000 |
| rtv_bench | HISTORY | 4B | Instruct | 4,608 | 100.0% | 0.304 | 0.330 | **0.589** | [0.574, 0.604] | +0.259 | 0.000 | 0.000 |
| rtv_bench | HISTORY | 4B | Thinking | 200 | 4.3% | 0.307 | 0.260 | **0.570** | [0.503, 0.640] | +0.310 | 0.010 | 0.010 |
| rtv_bench | HISTORY | 8B | Instruct | 4,608 | 100.0% | 0.304 | 0.270 | **0.568** | [0.554, 0.583] | +0.298 | 0.000 | 0.000 |
| rtv_bench | HISTORY | 8B | Thinking | 200 | 4.3% | 0.307 | 0.320 | **0.525** | [0.459, 0.599] | +0.205 | 0.000 | 0.000 |
| rtv_bench | RECENT | 4B | Instruct | 4,608 | 100.0% | 0.304 | 0.360 | **0.655** | [0.640, 0.671] | +0.295 | 0.000 | 0.000 |
| rtv_bench | RECENT | 4B | Thinking | 200 | 4.3% | 0.307 | 0.220 | **0.640** | [0.573, 0.707] | +0.420 | 0.000 | 0.000 |
| rtv_bench | RECENT | 8B | Instruct | 4,608 | 100.0% | 0.304 | 0.290 | **0.670** | [0.654, 0.684] | +0.380 | 0.000 | 0.000 |
| rtv_bench | RECENT | 8B | Thinking | 200 | 4.3% | 0.307 | 0.330 | **0.670** | [0.607, 0.732] | +0.340 | 0.000 | 0.000 |
| streaming_bench | HISTORY | 4B | Thinking | 200 | 6.2% | 0.250 | 0.390 | **0.675** | [0.608, 0.741] | +0.285 | 0.000 | 0.000 |
| streaming_bench | HISTORY | 8B | Thinking | 200 | 6.2% | 0.250 | 0.510 | **0.655** | [0.590, 0.721] | +0.145 | 0.000 | 0.000 |
| streaming_bench | RECENT | 4B | Instruct | 3,248 | 99.9% | 0.250 | 0.440 | **0.759** | [0.739, 0.777] | +0.319 | 0.000 | 0.000 |
| streaming_bench | RECENT | 4B | Thinking | 200 | 6.2% | 0.250 | 0.440 | **0.705** | [0.638, 0.768] | +0.265 | 0.000 | 0.000 |
| streaming_bench | RECENT | 8B | Instruct | 3,248 | 99.9% | 0.250 | 0.380 | **0.763** | [0.745, 0.782] | +0.383 | 0.002 | 0.002 |
| streaming_bench | RECENT | 8B | Thinking | 200 | 6.2% | 0.250 | 0.510 | **0.700** | [0.627, 0.770] | +0.190 | 0.000 | 0.000 |

## 16. Thinking − Instruct, matched questions, grey reference beside

Matched means the same qid, same input, same model, both arms. Bootstrap by video.
Estimates and intervals only; no difference here is labelled a finding or a null.

### 16.1 By dataset and input

| model | dataset | input | n matched | acc T | grey T | acc I | grey I | diff | 95% CI | flip rate | gen tok p50 T/I |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4B | ovo_bench | HISTORY | 400 | 0.507 | 0.360 | 0.545 | 0.350 | -0.037 | [-0.088, +0.016] | 0.282 | 359/2 |
| 4B | ovo_bench | RECENT | 400 | 0.552 | 0.340 | 0.547 | 0.350 | +0.005 | [-0.036, +0.046] | 0.180 | 265/2 |
| 4B | rtv_bench | HISTORY | 200 | 0.570 | 0.260 | 0.555 | 0.330 | +0.015 | [-0.050, +0.083] | 0.235 | 430/2 |
| 4B | rtv_bench | RECENT | 200 | 0.640 | 0.220 | 0.665 | 0.360 | -0.025 | [-0.084, +0.038] | 0.185 | 251/2 |
| 4B | streaming_bench | RECENT | 200 | 0.705 | 0.440 | 0.700 | 0.440 | +0.005 | [-0.046, +0.059] | 0.135 | 308/2 |
| 8B | ovo_bench | HISTORY | 400 | 0.568 | 0.370 | 0.557 | 0.390 | +0.010 | [-0.037, +0.055] | 0.225 | 211/2 |
| 8B | ovo_bench | RECENT | 400 | 0.593 | 0.360 | 0.560 | 0.370 | +0.033 | [-0.011, +0.073] | 0.198 | 199/2 |
| 8B | rtv_bench | HISTORY | 200 | 0.525 | 0.320 | 0.580 | 0.270 | -0.055 | [-0.116, +0.005] | 0.185 | 245/2 |
| 8B | rtv_bench | RECENT | 200 | 0.670 | 0.330 | 0.690 | 0.290 | -0.020 | [-0.066, +0.030] | 0.130 | 181/2 |
| 8B | streaming_bench | RECENT | 200 | 0.700 | 0.510 | 0.700 | 0.380 | +0.000 | [-0.053, +0.052] | 0.160 | 219/2 |

### 16.2 By task

Tasks with fewer than 20 matched questions are omitted; per-task n is small throughout and
the intervals are correspondingly wide.

| model | dataset | task | input | n | acc T | acc I | diff | 95% CI | flip rate |
|---|---|---|---|---|---|---|---|---|---|
| 4B | ovo_bench | ACR | HISTORY | 23 | 0.478 | 0.609 | -0.130 | [-0.318, +0.100] | 0.304 |
| 4B | ovo_bench | ACR | RECENT | 23 | 0.696 | 0.739 | -0.043 | [-0.250, +0.130] | 0.217 |
| 4B | ovo_bench | ASI | HISTORY | 23 | 0.696 | 0.696 | +0.000 | [-0.174, +0.174] | 0.174 |
| 4B | ovo_bench | ASI | RECENT | 23 | 0.609 | 0.609 | +0.000 | [-0.217, +0.217] | 0.261 |
| 4B | ovo_bench | ATR | HISTORY | 22 | 0.682 | 0.727 | -0.045 | [-0.143, +0.000] | 0.045 |
| 4B | ovo_bench | ATR | RECENT | 22 | 0.773 | 0.864 | -0.091 | [-0.227, +0.000] | 0.091 |
| 4B | ovo_bench | CRR | HISTORY | 67 | 0.552 | 0.478 | +0.075 | [-0.097, +0.210] | 0.463 |
| 4B | ovo_bench | CRR | RECENT | 67 | 0.418 | 0.373 | +0.045 | [-0.054, +0.178] | 0.224 |
| 4B | ovo_bench | EPM | HISTORY | 22 | 0.409 | 0.364 | +0.045 | [-0.158, +0.222] | 0.227 |
| 4B | ovo_bench | EPM | RECENT | 22 | 0.409 | 0.364 | +0.045 | [-0.105, +0.167] | 0.136 |
| 4B | ovo_bench | FPD | HISTORY | 22 | 0.773 | 0.909 | -0.136 | [-0.350, +0.048] | 0.227 |
| 4B | ovo_bench | FPD | RECENT | 22 | 0.864 | 0.864 | +0.000 | [-0.136, +0.130] | 0.091 |
| 4B | ovo_bench | HLD | HISTORY | 22 | 0.409 | 0.318 | +0.091 | [-0.091, +0.261] | 0.182 |
| 4B | ovo_bench | HLD | RECENT | 22 | 0.727 | 0.545 | +0.182 | [-0.050, +0.421] | 0.364 |
| 4B | ovo_bench | OCR | HISTORY | 22 | 0.636 | 0.864 | -0.227 | [-0.409, -0.050] | 0.227 |
| 4B | ovo_bench | OCR | RECENT | 22 | 0.864 | 1.000 | -0.136 | [-0.300, +0.000] | 0.136 |
| 4B | ovo_bench | OJR | HISTORY | 22 | 0.636 | 0.818 | -0.182 | [-0.429, +0.080] | 0.364 |
| 4B | ovo_bench | OJR | RECENT | 22 | 0.818 | 0.864 | -0.045 | [-0.150, +0.000] | 0.136 |
| 4B | ovo_bench | REC | HISTORY | 67 | 0.284 | 0.284 | +0.000 | [-0.095, +0.086] | 0.149 |
| 4B | ovo_bench | REC | RECENT | 67 | 0.194 | 0.149 | +0.045 | [+0.000, +0.102] | 0.045 |
| 4B | ovo_bench | SSR | HISTORY | 66 | 0.500 | 0.561 | -0.061 | [-0.214, +0.085] | 0.394 |
| 4B | ovo_bench | SSR | RECENT | 66 | 0.561 | 0.591 | -0.030 | [-0.150, +0.099] | 0.273 |
| 4B | ovo_bench | STU | HISTORY | 22 | 0.409 | 0.545 | -0.136 | [-0.381, +0.095] | 0.318 |
| 4B | ovo_bench | STU | RECENT | 22 | 0.682 | 0.682 | +0.000 | [-0.182, +0.182] | 0.182 |
| 8B | ovo_bench | ACR | HISTORY | 23 | 0.565 | 0.652 | -0.087 | [-0.278, +0.056] | 0.261 |
| 8B | ovo_bench | ACR | RECENT | 23 | 0.609 | 0.739 | -0.130 | [-0.333, +0.000] | 0.130 |
| 8B | ovo_bench | ASI | HISTORY | 23 | 0.783 | 0.696 | +0.087 | [-0.087, +0.261] | 0.174 |
| 8B | ovo_bench | ASI | RECENT | 23 | 0.783 | 0.696 | +0.087 | [-0.087, +0.261] | 0.174 |
| 8B | ovo_bench | ATR | HISTORY | 22 | 0.818 | 0.818 | +0.000 | [-0.136, +0.136] | 0.091 |
| 8B | ovo_bench | ATR | RECENT | 22 | 0.909 | 0.909 | +0.000 | [-0.136, +0.136] | 0.091 |
| 8B | ovo_bench | CRR | HISTORY | 67 | 0.657 | 0.522 | +0.134 | [+0.040, +0.204] | 0.284 |
| 8B | ovo_bench | CRR | RECENT | 67 | 0.507 | 0.403 | +0.104 | [+0.024, +0.217] | 0.284 |
| 8B | ovo_bench | EPM | HISTORY | 22 | 0.455 | 0.545 | -0.091 | [-0.333, +0.115] | 0.273 |
| 8B | ovo_bench | EPM | RECENT | 22 | 0.409 | 0.364 | +0.045 | [-0.105, +0.200] | 0.136 |
| 8B | ovo_bench | FPD | HISTORY | 22 | 0.773 | 0.864 | -0.091 | [-0.318, +0.105] | 0.273 |
| 8B | ovo_bench | FPD | RECENT | 22 | 0.818 | 0.818 | +0.000 | [-0.182, +0.191] | 0.182 |
| 8B | ovo_bench | HLD | HISTORY | 22 | 0.500 | 0.273 | +0.227 | [+0.000, +0.474] | 0.409 |
| 8B | ovo_bench | HLD | RECENT | 22 | 0.727 | 0.455 | +0.273 | [+0.048, +0.476] | 0.364 |
| 8B | ovo_bench | OCR | HISTORY | 22 | 0.773 | 0.682 | +0.091 | [-0.071, +0.273] | 0.182 |
| 8B | ovo_bench | OCR | RECENT | 22 | 0.909 | 0.955 | -0.045 | [-0.150, +0.000] | 0.045 |
| 8B | ovo_bench | OJR | HISTORY | 22 | 0.727 | 0.818 | -0.091 | [-0.318, +0.125] | 0.273 |
| 8B | ovo_bench | OJR | RECENT | 22 | 0.864 | 0.864 | +0.000 | [-0.136, +0.136] | 0.182 |
| 8B | ovo_bench | REC | HISTORY | 67 | 0.328 | 0.254 | +0.075 | [-0.033, +0.184] | 0.224 |
| 8B | ovo_bench | REC | RECENT | 67 | 0.179 | 0.164 | +0.015 | [-0.046, +0.082] | 0.075 |
| 8B | ovo_bench | SSR | HISTORY | 66 | 0.485 | 0.606 | -0.121 | [-0.224, -0.031] | 0.151 |
| 8B | ovo_bench | SSR | RECENT | 66 | 0.697 | 0.636 | +0.061 | [-0.068, +0.186] | 0.333 |
| 8B | ovo_bench | STU | HISTORY | 22 | 0.409 | 0.545 | -0.136 | [-0.300, +0.000] | 0.136 |
| 8B | ovo_bench | STU | RECENT | 22 | 0.500 | 0.682 | -0.182 | [-0.381, -0.042] | 0.182 |

(170 task-level cells computed, 48 with n>=20; all are in `analysis_rev2.json`.)

## 17. HISTORY − RECENT, matched questions (frame count 37 vs 9)

| model | dataset | arm | n matched | acc H | acc R | diff | 95% CI | flip rate | gen tok p50 H/R |
|---|---|---|---|---|---|---|---|---|---|
| 4B | ovo_bench | Instruct | 3,035 | 0.567 | 0.543 | +0.024 | [+0.002, +0.046] | 0.237 | 2/2 |
| 4B | ovo_bench | Thinking | 400 | 0.507 | 0.552 | -0.045 | [-0.099, +0.010] | 0.290 | 359/265 |
| 4B | rtv_bench | Instruct | 4,608 | 0.589 | 0.655 | -0.067 | [-0.079, -0.053] | 0.211 | 2/2 |
| 4B | rtv_bench | Thinking | 200 | 0.570 | 0.640 | -0.070 | [-0.142, +0.000] | 0.250 | 430/251 |
| 4B | streaming_bench | Thinking | 200 | 0.675 | 0.705 | -0.030 | [-0.094, +0.036] | 0.230 | 400/308 |
| 8B | ovo_bench | Instruct | 3,035 | 0.584 | 0.552 | +0.033 | [+0.009, +0.056] | 0.255 | 2/2 |
| 8B | ovo_bench | Thinking | 400 | 0.568 | 0.593 | -0.025 | [-0.079, +0.029] | 0.285 | 211/199 |
| 8B | rtv_bench | Instruct | 4,608 | 0.568 | 0.670 | -0.101 | [-0.114, -0.088] | 0.222 | 2/2 |
| 8B | rtv_bench | Thinking | 200 | 0.525 | 0.670 | -0.145 | [-0.211, -0.077] | 0.265 | 245/181 |
| 8B | streaming_bench | Thinking | 200 | 0.655 | 0.700 | -0.045 | [-0.113, +0.020] | 0.235 | 198/219 |


## 18. Observations on the revised tables

Estimates and intervals. Nothing in this section is called a finding or a null; §20 handles
status and §11's classification is revised there.

**On the grey control itself (§14).**

- The defect is gone on the face of the data: 94–99 distinct prompts per 100-request cell,
  against 1 in the invalid control.
- Grey accuracy is **not uniform across datasets relative to its floor**. On RTV-Bench it
  spans 0.220–0.360 against a 0.307 floor, i.e. at or around chance. On OVO-Bench it spans
  0.340–0.390 against 0.347, also at chance. On StreamingBench it spans 0.380–0.510 against a
  0.250 floor — 13 to 26 points above chance.
- On RTV-Bench the **majority-letter baseline (0.400) exceeds every grey cell** (0.220–0.360).
  With no visual input the models do worse than always naming the modal letter.
- The always-A baseline is 0.140 (OVO), 0.400 (RTV) and 0.240 (StreamingBench). On RTV it
  coincides with the majority baseline, so the invalid control's "always A" behaviour would
  have scored 0.400 there — above the corrected control's 0.220–0.360.
- n=100 per cell gives roughly ±0.09 intervals, so differences between individual grey cells
  of the same dataset are not separable at this n.

**On accuracy above grey (§15).**

- Every cell is above its own grey control, by **+0.145 to +0.420**.
- The margin is largest on RTV-Bench RECENT (+0.295 to +0.420) and smallest on
  StreamingBench HISTORY for 8B-Thinking (+0.145) and OVO-Bench HISTORY for 4B-Thinking (+0.147).
- RTV-Bench Instruct HISTORY is now at **100% coverage for both models** (4,608 each) after the
  remainder run; it was 80.6% / 91.7% before.

**On Thinking − Instruct (§16).**

- All ten dataset-level intervals contain zero. Point differences span −0.055 to +0.033.
- Per-question flip rates are **0.130–0.282**, five to twenty times the magnitude of the
  accuracy differences in the same cells.
- The grey columns show the two arms are not always working from the same no-visual baseline.
  On StreamingBench RECENT for 8B, grey is 0.510 (Thinking) against 0.380 (Instruct) while real
  accuracy is 0.700 for both — so the same accuracy sits +0.190 above grey for Thinking and
  +0.320 above grey for Instruct. On RTV-Bench the gap runs the other way for 4B (grey 0.220
  Thinking vs 0.360 Instruct). At n=100 per grey cell these differences are within interval
  overlap, so they are flagged as a direction to check, not a measured asymmetry.
- Thinking generates 181–430 tokens at p50 against Instruct's 2.

**On the by-task breakdown (§16.2).**

- 48 of 170 task-level cells have n ≥ 20. **6 of those 48 have intervals excluding zero**
  (OVO OCR, STU, SSR negative; OVO CRR ×2, HLD positive). At 48 cells and a 5% nominal rate,
  about 2.4 such cells are expected by chance alone, and **no multiplicity correction has been
  applied**. These are reported as the per-task estimates they are, not as per-task effects.

**On HISTORY − RECENT (§17).**

- The two fully-powered contrasts both show **37 frames scoring lower than 9 on RTV-Bench**,
  now on complete coverage: 4B Instruct −0.067 [−0.079, −0.053] and 8B Instruct
  −0.101 [−0.114, −0.088], n=4,608 each.
- The sign reverses on OVO-Bench Instruct: +0.024 [+0.002, +0.046] (4B) and
  +0.033 [+0.009, +0.056] (8B), both just excluding zero on complete coverage.
- Every Thinking contrast interval contains zero except 8B RTV-Bench, −0.145 [−0.211, −0.077].
- Prompt tokens are 3,109 (RECENT) and 12,587 (HISTORY) at p50 — a 4× input cost for the
  lower RTV score.
## 19. Cross-host frame identity vs the H100 run (added 2026-11-06 after merging `1be4422`)

§9 claimed `b1_frames.py` was "the pinned frame spec shared with the H100 run" and that the
recorded per-frame SHA-256 made "frame identity directly comparable with the H100 run". The
H100 results arrived on `origin/main` in commit `1be4422`, so that claim is now testable. Both
halves of it needed correcting, in opposite directions.

**The spec was not literally shared.** StudyB1-h100 renders frames with its own code
(`experiments/benchmarks/b1_common.py`, plus `b1_check_frames.py` and `b1_infer_vllm.py`), not
with `b1_frames.py`. The two implementations were written independently to the same written
specification.

**Frame identity nevertheless holds, and is now verified.** Joining the two runs' rows on
(`video_key`, query time, input) gives **13,672 overlapping requests** on OVO-Bench and
RTV-Bench (the two datasets whose videos fit on the H100 disk):

| quantity | result |
|---|---|
| frame timestamps identical (OVO) | 5,880 / 5,880 (100.0%) |
| frame timestamps identical (RTV) | 7,788 / 7,792 (99.9%) |
| frame count identical | 13,672 / 13,672 (100.0%) |
| **recorded PNG SHA-256 identical** | **0 / 13,672 (0.0%)** |

**The hash disagreement is an artifact of my own instrumentation, not of the frames.** The
recorded SHA-256 is taken over PNG *container* bytes, so it is sensitive to the zlib compression
level: this run used PIL's default (`compress_level=6`), StudyB1-h100 sets
`compress_level=1` (`b1_common.py:43`). Re-encoding flash's frames at level 1 and re-hashing,
on a seed-0 sample of 25 overlapping items:

| check | result |
|---|---|
| frame timestamps identical | 25 / 25 items |
| per-frame SHA-256 identical at `compress_level=1` | **645 / 645 frames (100%)** |
| per-frame SHA-256 identical at `compress_level=6` (as stored) | 0 / 645 |

Since PNG is lossless, identical bytes at a common compression level means the decoded, resized
pixel arrays are **bit-identical across the two hosts**. Frame selection and frame content both
agree; only the container encoding differed.

**Consequences, stated plainly:**

1. The per-frame SHA-256 as recorded is **not a valid cross-host frame-identity key**. A hash
   over raw pixel bytes (`Image.tobytes()`) would be, and is what the spec should have required.
   This affects the *verification mechanism*, not any measurement: within a single host the
   hashes are still a correct integrity check, and they did detect nothing wrong.
2. The frame-identity claim in §9 is **upheld on evidence** rather than by construction, for
   OVO-Bench and RTV-Bench. HERBench and StreamingBench cannot be checked this way because
   their videos were not copied to the H100.
3. This does **not** make flash and H100 accuracies comparable. The inference stacks still
   differ (§9: vLLM 0.19.1 / torch 2.10.0+cu128 / sm_86 / FA-2 versus the H100's stack), and
   StudyB1-h100's arms are 4B-Instruct, 32B-Instruct and 32B-Thinking, so only 4B-Instruct is a
   shared arm. Any such comparison must say so.

Evidence file: `results/benchmarks/study_b1_flash/crosshost_frame_check.json`.

---

## 20. Results consistency check, revision 2 (2026-11-06)

Re-run on the revised tables. Supersedes §10.

| # | check | outcome |
|---|---|---|
| 1 | cross-check vs committed measurements | **Partially possible now, and it agrees.** Still no valid prior for accuracy on these benchmarks (StudyD/StudyD2 are INVALID and not used). But commit `1be4422` brought StudyB1-h100, which overlaps this run on 13,672 requests, and the quantity that *is* shared — frame selection — agrees: identical timestamps on 100.0% of OVO and 99.9% of RTV overlapping items, identical frame counts on 100%. See §19. Accuracy is not cross-checked because the stacks differ and only 4B-Instruct is a shared arm. |
| 2 | physical plausibility | **PASS.** Unchanged rates: ~3,900–4,880 prompt tok/s, below the committed ~7,100 tok/s A6000 cold prefill. The grey2 run adds no latency claim. Caches off and recorded in `grey2/model_*/run_meta.json`. |
| 3 | distribution sanity | **PASS, with the constants explained.** Grey cells sharing a (dataset, input) question set report identical floor / majority / always-A columns — that is by construction, since the question set is deliberately shared across models and arms, not short-circuiting. Grey accuracies within such a group still vary (e.g. RTV RECENT: 0.360 / 0.220 / 0.290 / 0.330). Instruct `gen_tokens` p50 = max = 2 remains greedy letter+stop by construction. |
| 4 | definition audit | **PASS.** RECENT and HISTORY unchanged. The grey control's definition **changed** between revisions and both are recorded: revision 1 = one synthetic question, constant gold (INVALID, §7); revision 2 = real questions, pixels greyed (§14). The name "grey control" therefore has two definitions across this report and they must not be compared; §7 and `SUPERSEDED.md` label the old one. |
| 5 | claim linkage | **FLAGGED, unchanged.** Still measures `Q(f, w)`, which FORMULATION §Scoping states does not vary by node. Recorded as capability input for discussion, not as evidence on the coupling claim, and not citable as a gate result. |
| 6 | proxy validity | **PASS for the grey proxy now; one proxy demoted.** The grey control is now a valid proxy for "accuracy available without the visual channel" and is used as such. Separately, the per-frame PNG SHA-256 is **demoted**: it is not a valid cross-host frame-identity key (§19), only a within-host integrity check. The cross-host question was answered by re-encoding instead. |

### 20.1 Revised status of the §16 contrast

§11 classified the Thinking−Instruct accuracy null as INCONCLUSIVE for two reasons. One is
resolved, one is not.

- **Resolved:** the negative control. Step 4 now passes. Grey accuracy is measured per cell
  with a valid construction, and it changes the result — every real cell sits +0.145 to +0.420
  above its grey control, so the visual mechanism is operative and is not a constant.
- **Not resolved:** statistical power. Every Thinking cell remains a 4.3%–13.2% sample
  (n=200–400). The ten intervals are 8–17 points wide, which does not exclude accuracy
  differences the study would care about.

Therefore the §16 contrast is **not a settled negative**. The correct statement is narrower
and is what §18 gives: at n=200–400 per cell, no accuracy difference between Instruct and
Thinking is resolvable on these three benchmarks, while per-question correctness changes on
13–28% of matched questions. Per CLAUDE.md Rule 2 this is **inconclusive on accuracy for want
of power**, no longer inconclusive for want of a mechanism. Closing it needs more Thinking
coverage, not a better control.

The §17 HISTORY−RECENT contrast on RTV-Bench is on different footing: complete coverage,
n=4,608 per model, intervals excluding zero, and a mechanism confirmed present by the grey
control. It is reported as a measured property of these two input constructions on this
dataset, with no claim about context length, time-shifting, or any policy.
