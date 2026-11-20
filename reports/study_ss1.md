# StudySS1: single-shot workload candidates, device 4B benchmark (D136)

Picking the single-shot (SS) dataset for a new device type (an assistive camera / smart glasses
asking about what it sees now). A dataset qualifies only if the cloud 32B clearly beats the device
4B on it, with a preference for questions where the larger model resolves small or partial visual
detail better. This report covers the shared benchmark KIT and the DEVICE side (Qwen3-VL-4B-Instruct
on the Jetson AGX Orin under vLLM, the StudyORIN3 configuration). The H100 runs the identical kit
with the 32B later; the device-vs-cloud gap and the qualification verdict are decided there. No em
dashes.

HEAD at start (`git pull --ff-only`): `c76d4d0bacd1c1aaa33b610625dacb2add7053e6`.

## 0. Status

Device pass COMPLETE on both full sets, 0 errors. VizWiz-VQA val (4,319) scored locally with the
standard VQA accuracy; EgoThink (700) scored with the match scorer only (containment). The EgoThink
open-judge pass (scorer a, Mistral-7B-Instruct-v0.2) is DEFERRED to flash per the user's disk
ruling (2026-11-19): flash runs the Mistral judge on EgoThink alongside OpenEQA. The kit and the
raw per-question answers are pushed so flash can judge without re-running the device. The
cloud-vs-device gap awaits the H100 32B run on this same kit, so no dataset is qualified or rejected
in this report.

## 1. Licences (checked before any download; STOP gate)

| dataset | licence | research use | note |
|---|---|---|---|
| VizWiz-VQA (Gurari et al., CVPR 2018) | CC BY 4.0 (vizwiz.org) | yes, redistribution with attribution | validation split used |
| EgoThink (Cheng et al., CVPR 2024) | Apache-2.0 (github.com/AdaCheng/EgoThink; HF EgoThink/EgoThink) | yes | images bundled in the HF dataset, sourced from Ego4D (acknowledged upstream); not gated |

Neither licence forbids research use, so no STOP fired. Images are NOT committed (manifests and raw
text answers only).

## 2. The shared kit (committed; identical code for device and the later cloud run)

- `experiments/casestudy/ss1_kit.py`: prompts, preprocessing, scorers.
  - VizWiz prompt: `"{question}\nWhen the provided information is insufficient, respond with
    'Unanswerable'.\nAnswer the question using a single word or phrase."`
  - EgoThink prompt (verbatim from its `gpt_eval.py`): `"Please let your answer be as short as
    possible. Question: {question} Short answer:"`; `max_new_tokens` 30, except `assistance` and
    `navigation` (planning) which are 300.
  - Image preprocessing (shared, stated): open, convert to RGB, downscale only if the longest side
    exceeds 2048 px (Lanczos), re-encode as JPEG quality 90. The identical bytes go to both tiers;
    each model then applies its own released image processor, so the only preprocessing we impose is
    this re-encode and it is identical for device and cloud.
  - VizWiz scorer: the official VQA v2 answer normalisation (contractions, articles, punctuation,
    digit words) and acc = mean over the 10 leave-one-out subsets of min(matches/3, 1). The
    'unanswerable' class is scored exactly as the dataset scores it (it is just another answer
    string; the model is told it may answer Unanswerable).
  - EgoThink scorer (b), MATCH: normalised containment / exact match against the reference.
  - EgoThink scorer (a), JUDGE (implemented, run on flash not here): the repo's own
    `single-math-v2` judge prompt (`judge_prompts.jsonl`), a TEXT judge that is not shown the image
    and rates 0 / 0.5 / 1; to be run by Mistral-7B-Instruct-v0.2 (a non-Qwen3-VL open model, to
    avoid self-preference). `ss1_judge.py` reports judge mean and judge-vs-match agreement.
- `ss1_build_manifests.py`: builds the committed manifests (question id, image filename, question,
  references, strata) and the seeded (seed 0) stratified 300-question pilots. EgoThink images are
  decoded from the parquet to JPEG under the data root (not committed).
- `ss1_run.py`: the runner. One request at a time, greedy (temperature 0, seed 0), streaming to
  measure TTFT, writes per-question raw answer, cleaned answer, score, TTFT, prompt tokens, output
  tokens. Caching: vLLM prefix caching on, but every request carries a distinct image and question
  so no warm prefix is reused across questions, and a per-request cache_salt is sent; each question
  is a cold single-shot.
- `ss1_judge.py` (for flash), `ss1_analyse.py` (accuracy with 2,000-resample bootstrap CIs by
  stratum, TTFT p50/p90, tokens).

Manifests: 4,319 VizWiz val and 700 EgoThink questions. Multi-image or temporal items in EgoThink:
0 (each row is a single image). VizWiz image-quality flags (blur / framing / obstruction): NOT in
the VQA val release (they live in the separate VizWiz image-quality dataset), so the "partial or
degraded view" stratification is DEFERRED; the pilot and report stratify VizWiz by answer_type.
PROVISIONAL (user may ask for the quality-issues join as a separate step).

VizWiz val size: the official VQA 2020 validation split is 4,319 image/question pairs. The prompt's
3,173 is the 2018-paper split; corrected to 4,319 per the user ruling (2026-11-19). All 4,319 are
scored; the answerable-only slice (2,934, answerable = 1) is reported separately.

## 3. Device run configuration (Orin, Qwen3-VL-4B-Instruct, vLLM)

Served with the StudyORIN3 launcher `experiments/device/orin3_serve.sh` (vLLM 0.20.0, bf16,
max-num-seqs 1, prefix caching on, enforce-eager, seed 0). Two deviations from the StudyORIN3
defaults, forced by this box's state and recorded here:

- `gpu_memory_utilization` 0.22 and `max_model_len` 8192 (not 0.4 / 32768). A day-old orphaned vLLM
  engine core was holding 29 GiB of the 61 GiB unified memory; after it was cleared, 0.22 / 8192
  were kept because single-image VQA needs far less than 32k context (observed prompt tokens 1,550
  mean for VizWiz, 2,110 for EgoThink, well under 8,192) and the smaller budget is robust. 0 of
  5,019 requests hit the context limit.
- `FLASHINFER_DISABLE_VERSION_CHECK=1` with `VLLM_ATTENTION_BACKEND=FLASH_ATTN`, the workaround
  StudyORIN3 documented for this box (flashinfer-cubin 0.6.13 vs flashinfer 0.6.15 mismatch).

The committed serve script was not edited; both were passed as environment variables.

## 4. Device results (Qwen3-VL-4B, 0 errors on 5,019 questions)

### VizWiz-VQA val (4,319), standard VQA accuracy

| slice | n | VQA accuracy | 95% CI |
|---|---|---|---|
| all | 4,319 | 0.659 | [0.645, 0.672] |
| answerable only | 2,934 | 0.575 | [0.559, 0.590] |

By answer type: unanswerable 0.837 (n=1,385), yes/no 0.813 (195), number 0.654 (48), other 0.556
(2,691). The device is strong on the unanswerable class (the explicit Unanswerable option works) and
yes/no, weaker on open "other" answers, which is where a larger model is most likely to pull ahead.

TTFT p50 0.86 s / p90 1.41 s; total p50 1.45 s / p90 1.75 s; prompt tokens 1,550 mean, completion
4.0 mean. Wall time 5,625 s (94 min) for 4,319.

### EgoThink (700), match scorer only (containment); judge deferred to flash

Overall containment 0.471 [0.434, 0.507].

| area | n | containment | dimension | containment |
|---|---|---|---|---|
| Localization | 100 | 0.750 | location 0.760 / spatial 0.740 | |
| Object | 150 | 0.640 | affordance 0.440 / attribute 0.760 / existence 0.720 | |
| Reasoning | 150 | 0.487 | comparing 0.620 / counting 0.140 / situated 0.700 | |
| Forecasting | 100 | 0.450 | | |
| Activity | 100 | 0.320 | | |
| Planning | 100 | 0.090 | assistance 0.060 / navigation 0.120 | |

TTFT p50 1.47 s / p90 1.99 s; prompt tokens 2,110 mean, completion 3.4 mean. Wall time 1,158 s
(19 min) for 700.

Containment is a strict lower bound: the planning dimensions (0.06 to 0.12) and counting (0.14) are
long or free-form answers where exact-token containment fails even when the answer is right (for
example device "Planting flowers" against reference "cultivating plants"). This is exactly why
EgoThink's own protocol uses a judge, and why flash's Mistral judge pass (scorer a) is needed before
any EgoThink conclusion; the containment numbers here are the match-only floor, not the EgoThink
score.

### Full-run time and the 6 h gate

The pilot (300 + 300) ran cleanly, so the full sets were run. Total device wall time 113 min
(94 + 19), well under the 6 h gate, so no pilot-only fallback was needed. The 300-question pilots
are also committed (`*_pilot_device.json`) with their summaries.

## 5. Scorer agreement for EgoThink

Deferred with the judge. The kit computes judge-vs-match agreement in `ss1_judge.py`
(`judge_vs_containment_agreement`); flash reports it after the Mistral pass. The match floor already
shows the two will diverge most on Planning, Counting and Activity, where short containment
under-credits correct long answers.

## 6. Free disk (reported as required)

| | `/` (root, 57 G) | `/dev/shm` (31 G) |
|---|---|---|
| before finalize | 7.4 G avail (87% used) | 19 G avail (13 G used) |
| after | 7.4 G avail (87% used) | 19 G avail (13 G used) |

Flat, because Mistral-7B was NOT downloaded (user ruling). The datasets on `/dev/shm` are the 3.49 GB
VizWiz val images, the annotations, and the EgoThink parquet/extracted JPEGs (4.4 G total); the 4B
model snapshot is 8.3 G. All full-set images fit, so both full sets were run (not pilots only).

## 7. Results consistency check

- Cross-check: device TTFT and tokens are consistent with StudyORIN3 (text TTFT p50 ~0.25 s there;
  here 0.86 to 1.47 s with ~1,550 to 2,110 image prefill tokens added, as expected for single-image
  prefill). VizWiz 0.659 is a plausible 4B VLM accuracy; no committed prior exists for this
  device-type benchmark, so this row establishes it.
- Distribution sanity: strata reported with per-class n and bootstrap CIs; values vary across
  classes (0.56 to 0.84 VizWiz, 0.06 to 0.76 EgoThink), not a constant.
- Definition audit: VQA accuracy is the official VQA v2 procedure; EgoThink prompts and the judge
  are reproduced verbatim from the EgoThink repo.
- Caching: stated in section 2, cold single-shot.
- Proxy validity: EgoThink containment is a strict match floor, explicitly NOT the EgoThink score;
  the judge pass is required and deferred.

## 8. Provisional decisions (defaults; recorded)

1. No cloud latency or judge modelled on this box; device answers are the artifact. PROVISIONAL.
2. VizWiz quality-flag stratification deferred (flags not in the VQA release). PROVISIONAL.
3. `gpu_memory_utilization` 0.22 / `max_model_len` 8192 (robust for single-image VQA; 0 of 5,019
   hit the limit). PROVISIONAL.

## 9. Outputs and next

Committed under `results/casestudy/study_ss1/`: manifests (`vizwiz_val_manifest.jsonl`,
`egothink_manifest.jsonl`), seeded pilots, raw per-question device answers (`vizwiz_val_device.json`,
`egothink_device.json`, and the 300-question pilots), per-run summaries, and `ss1_manifest_meta.json`.
Kit scripts under `experiments/casestudy/`. This report. EXPERIMENTS row StudySS1.

Next: flash runs the Mistral-7B judge on EgoThink (scorer a) alongside OpenEQA, and the H100 runs
this identical kit with the 32B so the device-vs-cloud gap can be measured and the SS dataset
qualified.

---

# VizWiz: device 4B against cloud 32B (D142)

**Numbers only. No qualification threshold and no verdict:** D136's gate call is the user's and is
deliberately not made here, including by implication in ordering or framing.

Device: Qwen3-VL-4B on the Orin under vLLM 0.20.0+cu126, idle, one request at a time, cold per
image. Cloud: Qwen3-VL-32B (`0cfaf481...`, served as 32BI) on H100 NVL under vLLM 0.31.0, server
started fresh, idle, one request at a time, cold per image. Both 4,319 scored, 0 errors, greedy
`temperature=0 seed=0`. `run_order` verified as manifest order on both sides, 4,319 of 4,319.

## Two denominators, because the exclusions damage different axes

| set | n | mechanism | axis |
|---|---|---|---|
| shared images | 36 | warm multimodal encoder cache, keyed by image content | **TTFT only** |
| below min pixels | 28 | image area under the 65,536 px floor, device upscaled and cloud did not | **accuracy and TTFT** |

Disjoint (intersection 0, union 64). So **accuracy n = 4,291** (minus the 28 only) and
**TTFT n = 4,255** (minus both). A single excluded figure would either drop 36 questions from
accuracy for no reason or keep 36 contaminated ones in TTFT.

**The 36 are a CENSUS, not a bound, and the basis is three-fold rather than an equality.**
`mm_cache_hits_total = 36` against 36 candidates is the weakest of the three legs, because an exact
k = N can also arise from two offsetting errors. What grounds it:

1. **Instance separation.** The H100's prompt-token probes all went to a first server instance that
   stopped at 17:16; these counters belong to a second instance started 17:16:42 for this run, so
   no probe-induced hit can be inside the 36.
2. **Position matching at three checkpoints.** Hits landed at exactly the predicted positions,
   4 at request 151, 4 at 205 and 13 at 731. A spurious hit would have shown as an excess over
   prediction at the next checkpoint, and no excess was ever seen.
3. **The excess over 4,319 is accounted for by name.** `request_success_total` 4,322 and
   `mm_cache_queries_total` 4,323 exceed the 4,319 questions because the wrapper had already begun
   EgoThink when this file was stamped: the extra requests are Activity/000 to 003, a dimension
   with zero shared-image candidates and new image content, so none of the 36 can come from them.

The exclusion is therefore exact rather than conservative. Note also that `mm_cache_queries_total`
4,323 for 4,319 images means the multimodal queries side is non-vacuous too, the same property
established overwhelmingly for the prefix cache at 6,702,660 queries against 0 hits.

> **The counter value was read by regex, not by eye.** It sits inside a free-text stamp string
> where `=36` abuts the next `vllm:` token, and a `35` from a 17:49 snapshot at 3,876 requests was
> in circulation at the same time. Both numbers were correct for their own moment; only the stamp
> belongs in this file.

## Accuracy

| | n | device | cloud | paired diff (cloud − device) | 95% CI |
|---|---|---|---|---|---|
| full set | 4,319 | 0.6587 | 0.6650 | **+0.0063** | [−0.0044, +0.0169] |
| clean | 4,291 | 0.6584 | 0.6656 | **+0.0072** | [−0.0035, +0.0180] |

Paired bootstrap, 10,000 resamples, resampling question indices so the pairing is preserved.
**Both intervals include zero.**

## The 2x2, clean (n = 4,291), VQA accuracy cut stated at 0.5

| | n |
|---|---|
| both right | 2,523 |
| **cloud only** | **380** |
| **device only** | **349** |
| both wrong | 1,039 |

**The device-only cell is 349 of 4,291, against 380 cloud-only.** These are questions the 4B
answers and the 32B does not. Reported plainly because nothing else in the suite measures it and it
bears on D39's "per-request gain may be zero or negative".

Cut sensitivity, since VQA accuracy is graded and any 2x2 needs a stated cut:

| cut | both right | cloud only | device only | both wrong |
|---|---|---|---|---|
| 0.3 | 2,885 | 367 | 344 | 695 |
| 0.5 | 2,523 | 380 | 349 | 1,039 |
| 0.7 | 2,258 | 344 | 309 | 1,380 |
| 1.0 | 1,986 | 304 | 262 | 1,739 |

The two off-diagonal cells stay within 35 to 42 of each other at every cut.

## By stratum, clean

| stratum | n | device | cloud | diff | 95% CI |
|---|---|---|---|---|---|
| answer_type = unanswerable | 1,374 | 0.8354 | 0.8600 | **+0.0245** | [+0.0075, +0.0416] |
| answer_type = other | 2,675 | 0.5564 | 0.5599 | +0.0035 | [−0.0103, +0.0178] |
| answer_type = yes/no | 194 | 0.8119 | 0.7639 | −0.0479 | [−0.1000, +0.0052] |
| answer_type = number | 48 | 0.6542 | 0.5938 | −0.0604 | [−0.1875, +0.0625] |
| answerable = 0 | 1,374 | 0.8354 | 0.8600 | **+0.0245** | [+0.0075, +0.0416] |
| answerable = 1 | 2,917 | 0.5750 | 0.5740 | −0.0010 | [−0.0144, +0.0124] |

**Answerable-only is −0.0010 with CI [−0.0144, +0.0124].** The one interval excluding zero is
`unanswerable`, at +0.0245.

## TTFT

| | n | device p50 | cloud p50 |
|---|---|---|---|
| clean | 4,255 | 0.8618 s | 0.3225 s |

**The two columns now carry DIFFERENT labels, for different reasons, which is more informative
than when both were unverified.**

**Cloud: VERIFIED COLD BY A SAME-CONFIGURATION CONTROL ON A SEPARATE SERVER START, NOT VERIFIED
IN-PROCESS.** The positive control passed on all three arms on a fresh server on the identical
round-1 command: on three byte-identical repeats a unique salt gave 0 cached tokens while the same
salt gave 1,248 of 1,250, 1,232 of 1,245 and 1,232 of 1,238. So the field is populated on 0.31.0, a
hit does register, and a unique salt prevents one. Joined with the run's own 0 prefix hits on
**6,702,660 queried tokens**, the conclusion is cold. **The join assumes the instrument behaved
identically in the control process and the run process**, a same-binary same-command assumption,
stated rather than hidden.

**Device: PERMANENTLY UNVERIFIED-COLD.** vLLM 0.20.0 does not populate `cached_tokens` at all, and
the SS1 runner captured neither that nor the `/metrics` deltas, so no control could be constructed
after the fact.
Stack note: these device figures are the ORIN3 vLLM stack, whereas the committed device baseline
for robot recall is the ORIN2 in-process harness (D87, unexercised per D103c); the two must not be
placed side by side as one device's numbers.

## The resolution confound: measured, and the prediction held

Pre-registered before the run: equality on 4,291 of 4,319, divergence on exactly the 28, device
higher on each.

- **identical on 4,291 of 4,319 (99.35%)**
- **the differing set is EXACTLY the 28.** `differing_but_NOT_below` is empty and
  `below_but_NOT_differing` is empty.
- **the device is higher on every one of the 28** (cloud − device is negative on all, 0 elsewhere).

So the floor explains the divergence completely and nothing else contributes. The processor configs
agree on the three fields that carry the inference, **`patch_size` 16, `merge_size` 2 and
`longest_edge` 16777216**, with `temporal_patch_size` 2 and the same processor class also agreeing,
so the checkpoint-level confound is ruled out.

**One part of the prediction was wrong.** I bounded the per-item difference at 60 visual tokens
(64 − 4); the observed maximum is **74**. The reason is that `min_pixels` is a *minimum*, and the
upscale is then rounded up to a whole number of patch-merge blocks, so the device's visual count
exceeds 64 rather than equalling it. The bound was right in form and 14 tokens too tight.

Scaling test on **effective** post-cap area, which replaced the earlier `prompt_tokens` proxy:
Pearson r = 0.157, mean difference −3.135 in the smallest area decile and **0.000 in the largest**.
Consistent with a floor that acts only on small images.

The 28 by stratum, mild: other 16 of 2,691 (0.59%), unanswerable 11 of 1,385 (0.79%), yes/no 1 of
195 (0.51%), number 0 of 48. Under 1% of every stratum.

## Not produced

**By image-quality flag.** Not producible: the quality-issues release and VizWiz-VQA val use
different native filename numberings and no published crosswalk exists. See `compare_gates.json`
for the full diagnosis, including why the ~28000 offset is well motivated and still unverified, and
why the `v2_` prefix does not supply the missing 1,152.

## Reading the EgoThink stamp: the counters are CUMULATIVE

**Stated before that file is read, because the frame is easy to get wrong and expensive to chase
later.** This VizWiz file already proves the point: its totals include four EgoThink questions, so
both datasets ran on the same server instance and these counters are **monotonic across the whole
session** rather than per dataset.

So in the EgoThink stamp, expect:

| counter | expected | NOT |
|---|---|---|
| `mm_cache_hits_total` | about **52** (36 VizWiz + 16 EgoThink) | 16 |
| `mm_cache_queries_total` | about **5,019** | 700 |
| `prefix_cache_queries_total` | larger still | — |
| `prefix_cache_hits_total` | **0** | — |

Two readings to avoid, in opposite directions. A reader expecting 16 and seeing 52 would register a
3.25x over-run and hunt a cache leak that does not exist. A reader expecting 52 and seeing 52 must
**not** treat that as confirming EgoThink's 16 fired, because 36 of it is already banked from
VizWiz.

**EgoThink's own hit count is the DIFFERENCE between the two stamps, 52 − 36, and only that
difference speaks to EgoThink's 16 candidates.** It will be computed as a delta, not read as a
total.

---

# EgoThink: device 4B against cloud 32B (D142)

**Numbers only, no verdict.** Same two models, stacks and conditions as the VizWiz section. Both
700 scored, 0 errors, `run_order` verified manifest order 700 of 700 on both sides.

**Accuracy n = 700** (EgoThink has no below-min-pixels images). **TTFT n = 684**, excluding the 16
shared-image questions, which are a warm-encoder-cache timing artifact only.

**The 16 are a CENSUS.** `cache_check.per_dataset` gives EgoThink mm hits 16 of 16 candidates,
computed as a delta on the instance timeline by the only party that knows the instance boundaries.
One loose thread closed locally: the last snapshot captured 686 of 700 requests, so a candidate in
the uncaptured final 14 would have meant the 16 observed hits included a spurious one. **All 16
candidates sit at manifest positions 108 to 583, the latest 102 requests before the 686 boundary**,
so the truncation is irrelevant and the offsetting-errors mode is ruled out.

## Containment scorer

| | n | device | cloud | paired diff | 95% CI |
|---|---|---|---|---|---|
| full = clean | 700 | 0.4714 | 0.4771 | **+0.0057** | [−0.0229, +0.0343] |

**2x2 at cut 0.5:** both right 281 · cloud only 53 · **device only 49** · both wrong 317.
The interval includes zero.

## TTFT

| | n | device p50 | cloud p50 |
|---|---|---|---|
| clean | 684 | 1.4686 s | 0.4505 s |

Both columns **unverified-cold**, as for VizWiz. The prefix positive control is outstanding and is
the only thing that could upgrade the cloud side.

## Prompt-token parity: 100.000 percent, and it closes the template branch

Pre-registered: 100 percent equality, because **0 of 700 EgoThink images fall below the pixel
floor**, so neither side's budget binds on any of them.

**Result: 700 of 700 identical. One distinct difference value, zero.**

That is stronger than the VizWiz result in one specific way. EgoThink was never a constant-pixels
dataset (six distinct `(w,h)` pairs, areas spanning 1,175,040 to 4,915,200, a 4.2x range), so
identical totals across 700 questions with that much variation **within** the set means the text
side matches exactly as well as the visual side. **The chat template is therefore identical on both
sides, and the template branch of the confound decomposition is closed outright rather than
bounded.** Taken with VizWiz, where the only divergence was exactly the 28 sub-floor images, both
branches of the decomposition are now resolved: no template difference anywhere, and the pixel
difference confined to images below the floor.

---

## TTFT: `idle.json` and this run do not disagree, and the reason is measured

`idle.json` reports **p50 0.41 s** over 100 cold VizWiz questions on an idle engine at a median of
**1,976 prompt tokens**. This run reports cloud **p50 0.3225 s** over 4,255. A reader meeting those
two side by side would conclude the production run was faster than idle, which is the
caching-artifact signature consistency check 2 exists to catch. **It is a false alarm with a
mundane cause, and the cause is measurable rather than inferred.**

Cloud TTFT on this run is strongly prompt-length dependent:

| prompt tokens | n | TTFT p50 | p90 |
|---|---|---|---|
| 0–500 | 456 | 0.1013 | 0.1232 |
| 500–1,000 | 329 | 0.1934 | 0.2042 |
| 1,000–1,500 | 1,397 | 0.2862 | 0.2993 |
| 1,500–2,000 | 1,763 | 0.4483 | 0.4654 |
| 2,000–2,500 | 50 | 0.4528 | 0.4696 |
| 2,500–4,000 | 324 | 0.7203 | 0.7419 |

A 7x spread across the range. **This run's VizWiz prompts are p50 1,273 and p90 1,991, so
`idle.json`'s median of 1,976 sits at roughly this workload's p90**: its 100 questions are not a
representative sample, their median prompt being about 1.55x the workload's.

**Matched on prompt length the apparent paradox inverts, in the correct direction.** For prompts of
1,800 to 2,150 tokens, bracketing `idle.json`'s median, this run gives **p50 0.4485 s** against
`idle.json`'s **0.41 s**. The dedicated idle measurement is **faster**, by about 8 percent, which is
what an idle reference should be.

So neither figure is wrong and they measure different question mixes. **They must not be compared
directly, and 0.41 s is not the idle reference for a 0.3225 s workload.** This is a check-4
definition point of the same kind already recorded for "area": one name, two input distributions.
If `idle.json` is to serve as the reference against the 2 s SS deadline, its sample should match the
workload's token distribution, or the comparison should be made within prompt-length bands.

---

# The disagreement rate, both datasets and pooled

**This is a different claim from the paired difference, and a stronger one.** A null interval is
consistent with two models that agree almost everywhere. These numbers say the opposite: the two
models disagree constantly, and when they disagree **neither is reliably more often right**.

| dataset | n | cloud only | device only | disagree | rate |
|---|---|---|---|---|---|
| VizWiz (clean) | 4,291 | 380 | 349 | 729 | **16.99%** |
| EgoThink | 700 | 53 | 49 | 102 | **14.57%** |
| **pooled** | **4,991** | **433** | **398** | **831** | **16.65%** |

**The two models disagree on correctness for roughly one question in six.** Both rates rest on
large n and are tight enough to support that statement.

## When they disagree, the split is not distinguishable from a coin flip

| dataset | split | p(cloud right) | 95% CI on p | implied ratio range | includes 50/50 |
|---|---|---|---|---|---|
| VizWiz | 380 / 729 | 0.5213 | [0.4850, 0.5573] | [0.94, 1.26] | **yes** |
| EgoThink | 53 / 102 | 0.5196 | [0.4237, 0.6141] | [0.74, 1.59] | **yes** |
| pooled | 433 / 831 | 0.5211 | [0.4871, 0.5548] | [0.95, 1.25] | **yes** |

**Every interval contains exact parity, pooled across 831 disagreements included.** So "the cloud is
right more often when they disagree" is **not supported at any n available here**.

> **A correction to an earlier draft of this section.** It reported the two off-diagonal ratios,
> 1.089 and 1.082, as agreeing to within 0.007 and called that "hard to get by accident". That was
> wrong. EgoThink's ratio is known only to roughly [0.74, 1.59] on 102 disagreements, so two
> numbers matching to three decimals when one carries an interval of that width is coincidence, not
> corroboration. The two datasets are **consistent with a common ratio**; they do not establish
> one, and they do not establish that it differs from 1. This is consistency check 3 in its own
> form, values agreeing to more precision than the inputs vary, and it was committed before the
> interval on the split was computed.

**Parity inside the interval is a better result than a slight cloud edge**, and a different one. A
slight edge invites being banked; exact parity surviving 831 disagreements is a substantive
statement about escalation on these two workloads. It also sharpens D39 rather than softening it:
not merely zero-mean in the net, but **no detectable asymmetry in the disagreements that produce
the net**.

## Why the disagreement rate belongs above the confidence intervals

The VizWiz paired difference of +0.0072 is the **net of 380 cloud-only and 349 device-only
questions**. Reporting the net alone presents two large offsetting flows as a small effect. Check 3
covers a real effect averaged below its noise floor; **this is a pair of real effects cancelling**,
which reads identically in the mean and means something different. That observation does not depend
on the ratio being precise, only on both flows being large, which they are.

**D39 in its most literal form, measured rather than asserted:** per-request gain may be zero or
negative. For a scheduler the shape is **high-variance and approximately zero-mean** on these two
workloads: escalation costs per request, individual outcomes swing both ways, and no asymmetry in
who is right is detectable.

**No verdict and no threshold.** The disagreement rate is a fact about the data that the intervals
do not convey; what it implies for dataset qualification is the user's call.

---

# EgoThink, the judge column: the two scorers do not agree

**Mistral-7B-Instruct-v0.2 judge, native 0 / 0.5 / 1 scale, NO binarisation.** Same script, same
prompt, same post-fix parser on both sides. Paired on the **666** questions where both sides
produced a readable rating.

| scorer | device | cloud | paired diff | 95% CI | excludes zero |
|---|---|---|---|---|---|
| containment | 0.4714 | 0.4771 | +0.0057 | [−0.0229, +0.0343] | **no** |
| **judge (native)** | **0.7402** | **0.8026** | **+0.0623** | **[+0.0338, +0.0901]** | **yes** |

**The two scorers give different answers on the same 700 questions.** Containment finds no
detectable difference; the judge finds +0.062 with an interval clear of zero. Both are reported and
neither is adjudicated here.

**This is why two scorers were required rather than one.** It also coheres with the pre-registered
finding from the device-side judge pass: containment is weakest exactly where answers are long and
free-form, so on the dimensions where the gap is largest it is the scorer least able to see one.

Device rating distribution: 107 zeros, 132 halves, 427 ones.

## By dimension, device to cloud on the judge's native scale

| dimension | device | cloud | gap |
|---|---|---|---|
| Planning_assistance | 0.5408 | 0.7245 | **+0.184** |
| Reasoning_comparing | 0.6224 | 0.8061 | **+0.184** |
| Object_attribute | 0.8542 | 0.9375 | +0.083 |
| Planning_navigation | 0.4651 | 0.5465 | +0.081 |
| Reasoning_counting | 0.6778 | 0.7333 | +0.056 |
| Object_affordance | 0.7841 | 0.8295 | +0.045 |
| Localization_spatial | 0.8125 | 0.8542 | +0.042 |
| Activity | 0.7784 | 0.8196 | +0.041 |
| Forecasting | 0.6768 | 0.7172 | +0.040 |
| Localization_location | 0.9583 | 0.9896 | +0.031 |
| Object_existence | 0.8936 | 0.9149 | +0.021 |
| Reasoning_situated | 0.8265 | 0.8061 | **−0.020** |

The two largest gaps are `Planning_assistance` and `Reasoning_comparing`. `Reasoning_situated` is
the one negative.

## The judge's unparsed set is NOT missing at random, and the bias is nearly symmetric

The parse failure is the **judge** declining to emit a readable rating, not the answering model
failing, so it could concentrate where the rating is least certain. Measured rather than assumed,
using **containment as the yardstick because it is computable for every question whether or not a
rating was produced**:

| side | unparsed | rate | containment, parsed | containment, unparsed | gap |
|---|---|---|---|---|---|
| device | 18 / 700 | 2.571% | 0.4839 | **0.0000** | −0.484 |
| cloud | 21 / 700 | 3.000% | 0.4904 | **0.0476** | −0.443 |

**The exclusion is strongly informative.** All 18 device-side unparsed questions have containment
0, and 20 of 21 on the cloud side. The judge hedges almost exclusively on answers that containment
scores wrong, so dropping the unparsed set **removes near-exclusively failures and inflates both
judge means**.

**But the bias is nearly symmetric, so the paired difference is barely affected.** The two unparsed
sets are **not** disjoint: intersection 5, union 34, leaving 666 paired. Restricting each side to
the pair shifts its own mean by **+0.0049 (device)** and **+0.0058 (cloud)** — so the *differential*
is **+0.0009**, against a reported difference of +0.0623.

So the direction is known and the magnitude bounded: both means are inflated by roughly 0.005 in
absolute terms, and the paired difference by about 0.001. **The judge means should not be read as
estimates of absolute quality**, since they condition on the judge having been willing to rate.
The paired difference is robust to it.

---

# What is and is not judge-dependent

`egothink_compare_nocloudjudge.json` was committed before the judge finished, so the containment
deliverable exists independently. **Judge-dependent:** the native-scale judge means, the judge
paired difference, and the by-dimension judge table above. **Not judge-dependent:** every accuracy
figure, every 2x2 and cut sensitivity, every TTFT figure, both prompt-token parity results, and the
disagreement rate.

---

# Step 5: the length/verbosity alternative explanation, tested

**The alternative:** LLM judges are documented to reward length and fluency. Containment asks
whether the gold string is present and is largely indifferent to what surrounds it; a 0/0.5/1 judge
can reward register, completeness and hedging, all of which scale with model size independently of
correctness. **"The judge sees a difference containment cannot" and "the judge sees verbosity
containment correctly ignores" predict the same table.** These are separable with the data in hand.

## 1. The cloud does write longer answers, so the confound is live

| side | mean words | median | mean chars |
|---|---|---|---|
| device | 1.95 | 1.0 | 9.9 |
| cloud | **3.54** | 2.0 | 18.4 |

**1.81x on mean word count.** The confound is not dead and had to be tested rather than dismissed.

## 2. The judge DOES reward length, holding model and containment fixed

Within one side (model identity fixed) and within one containment stratum (correctness as
containment sees it fixed), comparing the shortest against the longest length tercile:

| side | containment | n | short tercile | long tercile | delta |
|---|---|---|---|---|---|
| device | 0 | 341 | 0.398 | 0.580 | **+0.181** |
| device | 1 | 325 | 0.921 | 0.991 | +0.069 |
| cloud | 0 | 334 | 0.554 | 0.685 | **+0.131** |
| cloud | 1 | 332 | 0.995 | 0.973 | −0.023 |

**A longer answer from the same model, scored the same by containment, receives a materially higher
judge rating.** On the device's containment-0 answers the effect is +0.181 from short to long
tercile. **The judge is partly scoring prose**, and this cannot be model quality because the model
is held fixed.

## 3. But most of the gap survives length matching

The sharpest single cell first: judge mean on **containment-0** answers is device 0.5205 against
cloud 0.6168, a gap of **+0.096**, while on containment-1 answers it is 0.9708 against 0.9895, a gap
of only +0.019. The cloud's advantage is concentrated where containment says the answer is wrong,
which is consistent with **both** readings and therefore does not separate them.

What separates them is matching on length. Restricting to the **387 question-pairs where both sides
produced the same word count**:

| | n | device | cloud | delta |
|---|---|---|---|---|
| matched-length pairs | 387 | 0.8204 | 0.8682 | **+0.0478** |

**+0.0478 of the +0.0623 overall survives, about 77 percent.** So length contributes to the gap but
does not account for most of it.

## Verdict on the alternative: partly operative, scoped, not dismissed

- **The length effect is real**, demonstrated within model and within containment stratum.
- **It does not explain the majority of the judge gap**: roughly three quarters survives at matched
  word count.
- **The limit on the 77 percent is COMMON SUPPORT, not a correctable bias.** This is the part that
  decides what could and could not fix it, so it is stated in those terms below.

**Reported as a scope condition, not a correction.** The judge column stands, with the caveat that
part of the +0.0623 is attributable to answer length rather than correctness, that the attributable
fraction is bounded at roughly a quarter on the matched-length evidence, and that this bound comes
from a short-answer-dominated subset. **The charitable and uncharitable readings of the scorer
disagreement are both partly right**, and the data says which share goes to each.

## What kind of limit the +0.0478 carries: common support, measured

The matched-length estimate collapsed onto one-word answers, and the reason matters for what a
reader should conclude.

**By range, the overlap is nearly complete.** Word counts present on both sides run 1 to 14, and
**99.8 percent of device answers and 95.6 percent of cloud answers fall inside it**. Only 1 device
answer and 17 cloud answers exceed it. So this is **not** a support violation in the strict sense.

**By density, the two distributions differ sharply inside that range.** The device puts 407 of 666
answers at one word (61 percent) against the cloud's 320 (48 percent), and the cloud carries far
more mass from 6 words upward. Exact matching therefore concentrates where both densities are
highest, which is the short end.

**And in the dimensions that drive the headline, matched pairs are thin:**

| dimension | n | device median | cloud median | exact-length matches |
|---|---|---|---|---|
| Planning_assistance | 49 | 5.0 | **11.0** | **10** |
| Planning_navigation | 43 | 3.0 | **8.0** | **8** |

**The judge gap is largest on `Planning_assistance` (+0.184), where the cloud's median answer is
11 words against the device's 5, and only 10 of 49 questions admit an exact-length comparison.**
Across both Planning dimensions, 18 matched pairs of 92 questions.

**So the honest statement of the limit, and one correction to a stronger version of it.** It is not
true that no comparison exists in the long regime: 18 matched Planning pairs exist, so the limit is
**thin overlap in the regime of interest rather than zero overlap**, and it is set by the device's
length distribution rather than being strictly structural. But 18 pairs cannot estimate a
length-adjusted Planning gap, and a larger question set would help only insofar as the device
produces long answers at all, which it mostly does not. **What a reader has, therefore:**

- a **real judge gap** of +0.0623 on the paired set;
- a **real judge length bias**, demonstrated within model and within containment stratum at +0.181;
- a **length-adjusted gap of +0.0478 identified on the short common support**, where both models
  write alike;
- and a **long tail where the two scorers disagree most and the length-adjusted comparison rests on
  18 pairs**, so no adjustment is usefully available there.

That closes the question rather than leaving a reader to suppose a larger n would settle it.

## The length bias is a finding about the instrument, not only a caveat

Stated separately because it stands on its own: **within one model and one containment stratum, the
judge gives longer answers higher ratings** — device containment-0, short tercile 0.398 against long
tercile 0.580, +0.181. Model fixed, containment fixed, so this cannot be a quality difference.
**The Mistral-7B judge is demonstrably sensitive to answer length independent of correctness**,
measured on this study's own data. That bears on any future use of this judge, not only on the
EgoThink comparison, and it is the second instrument finding from the judge pass after the parser
failure.

---

# The EgoThink judge passes its negative control, and the contrast with CODA-LM is the finding

The committed +0.0623 had an identity-style basis but **no permutation arm**. It now has one:
150 device questions judged with the ANSWER substituted from the next question, question and gold
kept.

| | mismatched mean | median | distribution | clears 0.5 |
|---|---|---|---|---|
| EgoThink | **0.0347** | 0.0 | 0.0 ×138, 0.5 ×2, 1.0 ×4 | **4.2%** |

Against **0.7431** for the same questions on their own answers: a gap of **+0.708** on a 0-to-1
scale. **138 of 144 mismatched answers scored exactly 0.** The judge reads content.

**So the judge column stands and is strengthened.** It is the only judge figure in either study
with both arms of its control. The withdrawal threshold was fixed before the numbers: the `>= 0.5`
binarisation is the one used for the agreement figure, so a large mismatched share clearing it would
have contaminated that too. It is 4.2 percent.

## Same judge, opposite verdicts, and the diagnosis is task demand not model size

| | scale | mismatched mean | normalised position in range | verdict |
|---|---|---|---|---|
| EgoThink | 0 / 0.5 / 1 | 0.0347 | 3.5% | **PASS** |
| CODA-LM | 1 to 10 | 6.88 | 65.3% | **FAIL** |

Same `Mistral-7B-Instruct-v0.2`, same temperature, same server. **Mismatched detection is roughly
nineteen times better on EgoThink in normalised terms.**

**A 7B too weak to grade would fail both.** It passes one and fails the other, so the binding
constraint is **task demand**: EgoThink asks whether a short answer matches a short gold, CODA-LM
asks for multi-object paragraph-level reference-grounded comparison. Same capacity, different
demand.

**This does not license "the CODA-LM prompt is bad."** That prompt is careful — it names accuracy,
hallucination suppression and correlation, and instructs explicitly against length bias. A weak
judge given a good rubric still cannot apply it, and CODA-LM's own pipeline used **GPT-4 with human
verification of its evaluations**, so the comparison was never 7B-against-rubric. **CODA-LM needs a
larger judge, not a prompt change. EgoThink needs nothing.**

The judge native-scale **means** remain non-absolute, for the separate and unchanged reason that the
unparsed set is strongly non-random and dropping it inflates both by about 0.005.
