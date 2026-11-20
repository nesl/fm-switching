# StudySS2: three CPS single-shot candidates, device 4B benchmark

Three candidate single-shot (SS) datasets for CPS-style device workloads, benchmarked on the device
4B under the same discipline as StudySS1 (shared kit, one prompt template per dataset, one
preprocessing path, greedy, one request at a time, cold per image, `_provenance`, raw per-question
answers). A dataset is a useful SS candidate only if the cloud 32B clearly beats the device 4B on
it; this report covers the KIT and the DEVICE side (Qwen3-VL-4B-Instruct on the Jetson AGX Orin
under vLLM, the StudySS1 / StudyORIN3 configuration). The H100 runs the identical kit with the 32B
later; the device-vs-cloud gap and the qualification verdict are decided there. No em dashes.

HEAD at start (`git pull --ff-only`): `e590e806b2309dbd8f58f5aab5f7fe268dcd4a35`.

## 0. Status

Device pass COMPLETE on the two datasets that cleared the licence gate: RefSpatial-Bench (277) and
RealWorldQA (765), both scored locally by the benchmarks' own metrics. CODA-LM is SKIPPED (see the
licence gate below) and not run. The kit and the raw per-question device answers are committed so
the H100 can run the identical kit with the 32B; the cloud-vs-device gap awaits that run, so no
dataset is qualified or rejected in this report.

## 1. Licences (checked before any download; STOP gate)

| dataset | licence | research use | note |
|---|---|---|---|
| RefSpatial-Bench (BAAI/RefSpatial-Bench; RoboRefer, arXiv 2506.04308) | Apache-2.0 | yes | 277 items (location 100, placement 100, unseen 77); no gating |
| RealWorldQA (xai-org/RealworldQA) | CC BY-ND 4.0 | yes (no derivatives) | 765 items; ND means do not redistribute modified images, so images are NOT committed |
| CODA-LM test (KaiChen1998/coda-lm) | annotations Apache-2.0; IMAGES CC BY-NC-SA 4.0 + Huawei Dataset Terms | SKIPPED | see below |

**CODA-LM is skipped.** The CODA-LM annotations are Apache-2.0, but the images are not in the HF
repo (it ships 19,638 JSON annotation files and no images); they come from the CODA dataset
(coda-dataset.github.io), under CC BY-NC-SA 4.0 plus Huawei "Dataset Terms" that restrict use to
non-commercial and PROHIBIT redistribution, and that you accept by downloading (a browsewrap
agreement; images are served via Google Drive / Baidu). The StudySS2 rule is explicit: "if any part
needs an agreement, skip CODA-LM and report." A terms-of-use you must agree to in order to obtain
the images is such an agreement, so the CODA-LM run is skipped: no CODA images were downloaded and
no answers were produced. The judge spec (gpt-4o-2024-05-13, the three stage prompts, the 1..10
rating parse) is preserved in `ss2_bench_kit.py` (`CODA_LM_*`) so the user can lift the skip; if lifted,
CODA images must still never be redistributed.

RefSpatial and RealWorldQA cleared the gate. Images are NOT committed for either (RefSpatial by the
project's manifests-only discipline; RealWorldQA additionally by the ND licence).

## 2. The shared kit (committed; identical code for device and the later cloud run)

- `experiments/casestudy/ss2_bench_kit.py`: prompts, preprocessing, scorers. (Named
  `ss2_bench_kit.py`, not `ss2_kit.py`, because a parallel StudySS2 session had already pushed its
  own `ss2_kit.py` holding the CODA-LM 1..10 judge parser; the two modules are distinct and coexist.
  The H100 32B benchmark run imports `ss2_bench_kit`.)
  - Image preprocessing (shared, identical to StudySS1): open, convert to RGB, downscale only if the
    longest side exceeds 2048 px (Lanczos), re-encode as JPEG quality 90. The identical bytes go to
    both tiers; each model then applies its own released image processor, so the only preprocessing
    we impose is this re-encode and it is identical for device and cloud.
  - RefSpatial prompt: the official RoboRefer `get_prompt` Qwen branch (`test_benchmark.py`):
    `"Locate {object} in this image and output the point coordinates in JSON format."` Qwen3-VL is a
    Qwen VLM, so this is the benchmark's own prompt for both tiers.
  - RefSpatial scorer: reproduced from `summarize_acc.py` `compute_accuracy`: load the GT binary
    mask (PIL open, /255, channel 0 if 3-D, binarise `>0`); per-sample accuracy = fraction of
    predicted points landing inside the mask (looked up at `mask[y, x]`); out-of-bounds points count
    as explicit zeros; split-level mean. See the coordinate convention in section 3.
  - RealWorldQA prompt: the dataset's own `question` text, unchanged (the question already embeds
    its instruction and, for MCQ, its lettered options); the lmms-eval default adds nothing.
  - RealWorldQA scorer: reproduced from lmms-eval `realworldqa_process_results`. MCQ iff the gold
    answer is a single letter in {A,B,C,D}; MCQ scored by conservative option-letter extraction
    (honours `\boxed{}`/`<answer>`, an explicit "Answer: X", else a bare final letter, abstains on
    ambiguity) compared to the gold letter; free-form scored by exact match after
    `lower().strip().rstrip(".")`. MCQ and free-form are reported as separate subsets.
  - CODA-LM judge spec recorded (not run): `CODA_LM_GENERATION_PROMPTS`, `CODA_LM_JUDGE_*`,
    `parse_rating_1to10`.
- `ss2_build_manifests.py`: builds the committed manifests (question id, image FILENAME, task text,
  reference, strata) and seeded smoke sets from the parquet staged on `/dev/shm`. Images decoded to
  lossless PNG under the data root (NOT committed) so the only imposed preprocessing is the shared
  q90 re-encode.
- `ss2_run.py`: the runner. One request at a time, greedy (temperature 0, seed 0), streaming to
  measure TTFT, writes per-question raw answer, cleaned answer, score, TTFT, prompt tokens, output
  tokens, and a `_provenance` stamp. The SAME runner serves device and the later cloud 32B.
- `ss2_analyse.py`: accuracy with 2,000-resample bootstrap CIs by stratum, TTFT p50/p90, tokens.

Manifests: 277 RefSpatial (location 100 / placement 100 / unseen 77) and 765 RealWorldQA (MCQ 438 /
free-form 327). Multi-image or temporal items: 0 (each row is a single image).

## 3. Mechanism / scoring validation (before the full sweep; CLAUDE.md Step 2b)

This is a measurement benchmark, not a causal-policy comparison, so the relevant check is Step 2b:
confirm the scoring path produces a meaningful (non-artifact) number before the sweep. RealWorldQA
is deterministic text matching and was confirmed on an 8-item smoke (MCQ letters extracted and
matched, free-form normalised and matched). RefSpatial point scoring hinges on the coordinate
convention and WAS AN ARTIFACT UNTIL VALIDATED:

- Qwen3-VL emits point coordinates NORMALISED to 0..1000 (`x_norm = x_px / W * 1000`), not the
  absolute pixels the RoboRefer Qwen branch assumed (that branch targeted Qwen2.5-VL). On the 9-item
  smoke these 640x480 images are within Qwen3-VL's pixel budget so no internal resize happens, yet
  predicted coordinates reached y=971 and x=800, which absolute pixels of a 640x480 image can never
  exceed. Under the "absolute" convention 4 of 9 points fell out of bounds and the mean accuracy was
  0.000, a pure scoring artifact. Under "norm1000" all 9 points were in bounds and the mean accuracy
  was non-zero (0.111 on the smoke). `COORD_MODE = "norm1000"` is locked in the kit and applied
  identically to device and cloud. Had the sweep been run under the default, it would have reported
  a false 0.000 for the 4B.

## 4. Device run configuration (Orin, Qwen3-VL-4B-Instruct, vLLM)

Served with the StudyORIN3 launcher `experiments/device/orin3_serve.sh` (vLLM 0.20.0, bf16,
max-num-seqs 1, prefix caching on, enforce-eager, seed 0), the StudySS1 configuration. Two
deviations from the StudyORIN3 defaults, recorded: `gpu_memory_utilization` 0.22 and `max_model_len`
8192 (robust for single-image VQA; observed prompt tokens 311 mean for RefSpatial and 1,343 for
RealWorldQA, well under 8,192, and 0 of 1,042 requests hit the context limit), and
`FLASHINFER_DISABLE_VERSION_CHECK=1` with
`VLLM_ATTENTION_BACKEND=FLASH_ATTN` (the flashinfer-cubin 0.6.13 vs flashinfer 0.6.15 workaround).
The committed serve script was not edited; both were passed as environment variables.

**mm-processor settings (recorded as required):** `orin3_serve.sh` passes NO `--mm-processor-kwargs`,
so the released Qwen3-VL-4B image-processor defaults are used: `size = {shortest_edge: 65536,
longest_edge: 16777216}` (min / max pixels), `patch_size 16`, `merge_size 2`, `temporal_patch_size
2` (from the installed `preprocessor_config.json`). This matches the StudySS1 device configuration.
The H100 32B run should record its own mm-processor settings; if the H100 overrides the pixel budget
(as the StudySS1 cloud run did), note that only the min-pixels floor differs and it binds only on
images below ~256x256 area, which neither dataset contains at scale.

## 5. Device results (Qwen3-VL-4B)

### RefSpatial-Bench (277), fraction of predicted points inside the GT mask

Pooled point accuracy 0.251 [0.200, 0.305] (n-weighted over 277; the benchmark itself reports per
split, so the per-split rows are the primary figures).

| split | n | point accuracy | 95% CI |
|---|---|---|---|
| location | 100 | 0.335 | [0.240, 0.430] |
| placement | 100 | 0.230 | [0.150, 0.320] |
| unseen | 77 | 0.169 | [0.091, 0.247] |

By step (reasoning complexity, number of anchors / relations): step1 0.433 (n=30), step2 0.241
(110), step3 0.282 (85), step4 0.154 (39), step5 0.000 (13). Accuracy falls with complexity and the
13 hardest 5-step items are all missed. Only 1 of 277 answers failed to parse to a point (n_points
mean 1.0), so 0.251 is a real pointing score, not a parse artifact. The weakness on open spatial
referring (placement 0.23, unseen 0.17, and the step-complexity falloff) is exactly where a larger
model is most likely to pull ahead; that gap is the H100's to measure.

TTFT p50 0.15 s / p90 0.21 s; total p50 1.99 s / p90 2.45 s; prompt tokens 311 mean (640x480 images
are few visual tokens), completion 33 mean (the JSON point). Wall time 580 s (10 min) for 277.

### RealWorldQA (765), exact match after the benchmark normalisation

| slice | n | exact match | 95% CI |
|---|---|---|---|
| all | 765 | 0.655 | [0.621, 0.689] |
| MCQ (gold in {A,B,C,D}) | 438 | 0.637 | [0.596, 0.680] |
| free-form | 327 | 0.679 | [0.630, 0.728] |

The two subsets are close (free-form marginally higher), so there is no obviously harder slice for
the 4B here; whether the 32B separates on either subset is the H100's to decide.

TTFT p50 0.90 s / p90 1.19 s; total p50 0.96 s / p90 1.25 s; prompt tokens 1,343 mean, completion
2.0 mean (short answers). Wall time 764 s (13 min) for 765. Combined device wall time 1,344 s
(22 min) for 1,042 items, far under any time gate.

## 6. Free disk (reported as required)

| | `/` (root, 57 G) | `/dev/shm` (31 G) |
|---|---|---|
| before downloads | 7.2 G avail (87% used) | 19 G avail |
| after runs | 7.1 G avail (87% used) | 17 G avail |

Essentially flat on `/`. The `/dev/shm` delta is 1.9 G of ephemeral staged data (RefSpatial +
RealWorldQA parquet and the decoded PNG images, NOT committed). All full-set images fit, so both
full sets were run (no pilot-only fallback). CODA images were NOT downloaded (the CODA-LM skip). The
HF download had to disable the xet backend (`HF_HUB_DISABLE_XET=1`) to get past an IP rate limit on
xet token requests; the classic LFS path pulled the five parquet shards in 10 s.

## 7. Results consistency check

1. Cross-check against committed measurements: no prior committed value exists for these two
   datasets on this device-type benchmark (new rows). The timing and token counts are consistent
   with StudySS1 / StudyORIN3: RealWorldQA TTFT p50 0.90 s at ~1,343 image-prefill tokens matches
   StudySS1 VizWiz (0.86 s at ~1,550 tokens); RefSpatial 0.15 s at only 311 tokens (640x480 images)
   is proportionately smaller. No disagreement greater than 2x.
2. Physical plausibility: RealWorldQA prefill ~1,343 tokens at 0.90 s TTFT is ~1,500 tok/s;
   RefSpatial 311 tokens at 0.15 s is ~2,000 tok/s. Both sit in the Orin single-image prefill regime
   (StudySS1 ~1,500 to 1,800 tok/s); nothing is faster than the committed curves.
3. Distribution sanity: strata reported with per-class n and bootstrap CIs; values vary across
   classes (RefSpatial 0.00 to 0.43 across splits and steps, RealWorldQA 0.64 to 0.68 across
   subsets), not constants. RefSpatial step5 = 0.000 is a real floor on the 13 hardest items,
   reported with its n, not an averaged-out constant.
4. Definition audit: RefSpatial point accuracy = summarize_acc.py fraction-of-points-in-mask
   (per-split mean); RealWorldQA exact match = lmms-eval realworldqa_process_results (MCQ letter
   extraction / free-form lower-strip-rstrip). Reproduced from the repos; the coordinate convention
   (norm1000) is the one validated in section 3.
5. Claim linkage: this is the SS case study (dataset qualification for a new device type). The
   device numbers are one half of the device-vs-cloud gap that qualifies a dataset; they do not by
   themselves bear on a FORMULATION claim, and the qualification verdict is the H100's. No measured
   quantity is scoped out.
6. Proxy validity: both metrics are the benchmarks' own metrics, not proxies. RefSpatial COORD_MODE
   is a reproduction choice (validated in section 3), not a proxy substitution.
7. Control validation: there is no before/after or arm-versus-baseline comparison here (a single
   device measurement). The positive control is the smoke-set plumbing check of section 3, which
   confirmed non-artifact scoring on both datasets before the full sweep; it is what caught the
   RefSpatial coordinate-convention artifact.

## 8. Provisional decisions (defaults; recorded)

1. CODA-LM skipped on the CODA image terms gate (user rule). PROVISIONAL (user may lift the skip;
   the judge spec is kept in the kit).
2. RefSpatial `COORD_MODE = "norm1000"` (Qwen3-VL normalised coordinates), validated on the smoke.
   PROVISIONAL (the H100 must confirm the 32B uses the same convention; the kit applies it to both).
3. RefSpatial prompt = the RoboRefer Qwen-branch prompt; RealWorldQA prompt = the dataset question
   verbatim (lmms-eval default). PROVISIONAL.
4. `gpu_memory_utilization` 0.22 / `max_model_len` 8192, and no `--mm-processor-kwargs` (released
   defaults). PROVISIONAL.
5. RealWorldQA MCQ vs free-form split by gold-answer-in-{A,B,C,D} (lmms-eval rule). PROVISIONAL.

## 9. Outputs and next

Committed under `results/casestudy/study_ss2/`: manifests (`refspatial_manifest.jsonl`,
`realworldqa_manifest.jsonl`), seeded smoke sets, raw per-question device answers
(`refspatial_device.json`, `realworldqa_device.json`), per-run summaries, and
`ss2_manifest_meta.json`. Kit scripts under `experiments/casestudy/`. This report. EXPERIMENTS row
StudySS2.

Next: the H100 runs this identical kit with the 32B so the device-vs-cloud gap can be measured and
each dataset qualified as an SS candidate (a dataset qualifies only if the 32B clearly beats the 4B,
preferring small or partial-detail questions). CODA-LM remains skipped unless the user lifts the
image terms gate.

## 10. StudySS2 compare: paired device against cloud (numbers only, no verdict)

Device Qwen3-VL-4B on the Orin (`jetson_orin`, `_provenance` present), cloud Qwen3-VL-32B-Instruct
at `0cfaf481` on the H100 NVL, vLLM 0.31.0+cu129, served as `32BI`. Both greedy, temperature 0,
seed 0, one request at a time, idle, per-request `cache_salt`. Paired on `qid`: RefSpatial 277 of
277, RealWorldQA 765 of 765, zero device-only and zero cloud-only rows, zero errors on either side.

**No verdict here. D136's gate call is the user's.** The numbers are reported per dataset and subset
as D142 requires; nothing below is a qualification statement.

### 10.1 Positive control, run before the comparison was read

Check 7 asks that the control arm reproduce its own committed numbers, not merely agree with the
treatment. The device column is recomputed here from the raw per-question rows and must match the
committed device summaries exactly.

| quantity | this compare | committed summary | agree |
|---|---|---|---|
| RefSpatial device, pooled point accuracy | 0.250903 | 0.2509025 | yes |
| RefSpatial device, `location` | 0.3350 | 0.335 | yes |
| RefSpatial device, `placement` | 0.2300 | 0.23 | yes |
| RealWorldQA device, exact match | 0.654902 | 0.6549019 | yes |
| RealWorldQA device, `free_form` | 0.6789 | 0.6788990 | yes |
| RealWorldQA device, `mcq` | 0.6370 | 0.6369863 | yes |

### 10.2 Accuracy, paired bootstrap (10,000 resamples, seed 0)

| dataset / subset | n | device | cloud | cloud minus device | 95 % CI | excludes 0 |
|---|---|---|---|---|---|---|
| **RefSpatial, all** | 277 | 0.2509 | 0.3714 | **+12.05 pp** | [+5.94, +18.29] | yes |
| RefSpatial `location` | 100 | 0.3350 | 0.5133 | **+17.83 pp** | [+7.50, +28.50] | yes |
| RefSpatial `placement` | 100 | 0.2300 | 0.2856 | +5.56 pp | [-5.33, +16.11] | **no** |
| RefSpatial `unseen` | 77 | 0.1688 | 0.2987 | **+12.99 pp** | [+2.60, +23.38] | yes |
| **RealWorldQA, all** | 765 | 0.6549 | 0.7124 | **+5.75 pp** | [+2.35, +9.15] | yes |
| RealWorldQA `mcq` | 438 | 0.6370 | 0.7146 | **+7.76 pp** | [+3.20, +12.33] | yes |
| RealWorldQA `free_form` | 327 | 0.6789 | 0.7095 | +3.06 pp | [-2.14, +8.26] | **no** |

Scorer per subset, stated so an MCQ-against-free-form contrast is not read as a model effect:
RefSpatial is the fraction of predicted points inside the ground-truth mask (`point_accuracy`,
`norm1000` coordinate mode on both tiers); RealWorldQA is exact match after the benchmark's own
normalisation, which is letter match on `mcq` and normalised string match on `free_form`.

### 10.3 The 2x2, and the disagreement split

| dataset | both right | cloud only | device only | both wrong | disagree |
|---|---|---|---|---|---|
| RefSpatial | 45 | 58 | 25 | 149 | 83 of 277 (30.0 %) |
| RealWorldQA | 435 | 110 | 66 | 154 | 176 of 765 (23.0 %) |

Cloud-right share of the disagreements, with Wilson 95 % intervals: RefSpatial **0.6988
[0.5931, 0.7869]**, RealWorldQA **0.6250 [0.5515, 0.6931]**. **Both exclude 0.5.** This is the
opposite of StudySS1, where every such interval including the pooled one contained parity and the
claim "the cloud is right more often when they disagree" was withdrawn as unsupported. On SS2 the
interval supports it on both datasets. The register is a pre-specified binary scorer on both tiers,
not a judge.

### 10.4 Prompt-token parity: the resolution confound is cleared as a census

| dataset | n | identical counts | max difference |
|---|---|---|---|
| RefSpatial | 277 | **277 of 277 (100 %)** | 0 |
| RealWorldQA | 765 | **765 of 765 (100 %)** | 0 |

**1,042 of 1,042 questions identical**, so the two tiers were shown the same visual input and no
resolution confound exists on SS2. StudySS1 had 28 VizWiz images diverge; that set is empty here,
and it is empty for a measurable reason rather than by luck.

**The sub-floor exclusion is an empty CENSUS, not an unchecked assumption**
(`ss2_below_min_pixels.json`). Both manifests carry `width` and `height` on every row, so every
image was measured: RefSpatial areas run 196,608 to 307,200 px and RealWorldQA 261,668 to
2,158,080 px, against a 65,536 px `min_pixels` floor on the device and 4,096 px on the cloud. **The
smallest SS2 image is 3.0x the device floor**, and the kit's 2048 longest-side cap only shrinks the
longest side, leaving every effective area above the floor as well. So neither tier upscaled and the
accuracy denominator loses nothing.

### 10.5 TTFT, and why the repeated-image set had to leave the timing column

Two exclusion sets, not merged, because they damage different axes. Below-floor is empty, so
accuracy keeps every question: **accuracy n = 277 and 765**. The repeated-image set is TTFT-only:
**TTFT n = 91 (RefSpatial) and 762 (RealWorldQA)**.

| dataset | tier | p50 full set | p50 cold only | p90 cold only |
|---|---|---|---|---|
| RefSpatial | device | 0.1528 | **0.1984** | 0.2115 |
| RefSpatial | cloud | 0.0848 | **0.1218** | 0.1324 |
| RealWorldQA | device | 0.8984 | 0.8984 | 1.1899 |
| RealWorldQA | cloud | 0.3022 | 0.3022 | 0.3787 |

On RefSpatial, **186 of 277 questions (67 %) sit on a repeated image**, so reading the full-set
cloud p50 of 0.0848 s as a cold number would understate cold cloud TTFT by about **1.4x**. On
RealWorldQA only 3 of 765 repeat, and the column does not move.

**Register: the repeated-image set is a CENSUS, not a constructed bound.** The candidate lists were
built as bounds, the questions that *could* be served warm. The server's own counters close it: the
cumulative `vllm:mm_cache_hits_total` is 186 after RefSpatial and 189 after RealWorldQA, so the
per-dataset observed hits are **186 and 3**, equal to the candidate counts of **186 and 3**. The
exclusion is therefore exactly the warm-served set.

Prefix caching, separately: `prefix_cache_hits_total` is **0** on **1,087,829** queried tokens
across both datasets, so the text prefix cache is isolated, as the per-request `cache_salt`
intends. The 32B server command carries both `--no-enable-prefix-caching` and
`--enable-prefix-caching`; the later flag wins, prefix caching was on, and the zero hit count is
what makes the isolation an observation rather than a flag reading.

### 10.6 Both tiers served the repeats warm, measured within-image

The cloud's warm hits are confirmed by its own counters. The device file instead **declares**
"distinct image+task per request so no warm reuse; cold single-shot". That is a declaration, and
`cache_salt` isolates the **text** prefix cache only: the multimodal encoder cache is keyed by image
**content**, which no salt touches.

A between-subsets comparison cannot settle it, because the repeat set and the clean set differ in
image-size composition. The test therefore holds composition fixed: **within each of the 61 shared
images**, first occurrence in run order against later ones (`ss2_warm_within_image.py`).

| RefSpatial | n | device p50 | cloud p50 | device prompt tokens p50 |
|---|---|---|---|---|
| first occurrence (cold) | 61 | 0.2096 | 0.1244 | 335 |
| later occurrences (warm) | 186 | **0.1520** | **0.0829** | 337 |
| never on a shared image | 30 | 0.1822 | 0.1055 | 226 |

**Same images, prompt tokens 335 against 337**, and the later requests are **27.5 % faster on the
device** and **33.4 % faster on the cloud**. RealWorldQA points the same way on 3 repeats: device
10.7 %, cloud 13.0 % faster warm.

The between-subsets direction confirms it and rules out composition as the cause: removing the
repeats **raises** the device p50 from 0.1528 to 0.1984, while the clean set holds **more** small
images (41 of 91 at 196,608 px against 28 of 186), which would make it faster, not slower. So
composition works against the observed direction and cannot produce it.

**Register: OBSERVED, within-image, both tiers.** It is not a controlled rerun; no cold repeat of
the same questions was run, so this is an observational inference from run order with composition
held fixed rather than adjusted for. The consequence is a correction to a committed caching string,
not to any accuracy number: **"cold per image" is false for any dataset whose images repeat**, and
RefSpatial repeats 67 % of the time.

### 10.7 CODA-LM: no data, and a judge that fails its control

**No CODA-LM answers exist on either tier.** `results/casestudy/study_ss2/` holds no CODA-LM device
or cloud answer file, so no CODA-LM comparison is reported and none is possible from committed data.

Independently, the Mistral-7B judge on CODA-LM's own 1-10 prompt **FAILS** its negative control:
mismatched answers score a mean of **6.88** on the 1-10 scale, **65.3 % of the usable range**, with
10 of 74 at exactly 10.0 and 68 % clearing the pre-registered 6.0 cut. That is a stopping condition
on the per-task means and the cut was not moved. The EgoThink judge **passes** the same control
(mismatched 0.0347, 3.5 % of range, 138 of 144 at exactly 0), so with one model, temperature and
server the instrument is about **19x** better at detecting a mismatch on EgoThink. The binding
constraint is task demand, not judge size; CODA-LM needs a larger judge.

### 10.8 Two defects fixed in `ss2_compare.py` before it could run

Both were field-path errors in a script written before the data existed, and both are
implementation fixes under CLAUDE.md, applied and reported rather than discussed first.

1. **`score_of` raised on row one of both datasets.** It looked for `vqa_accuracy` / `containment` /
   `accuracy`; the SS2 kit writes **`point_accuracy`** and **`exact_match`**. Replaced with a
   per-dataset key lookup rather than a scan that could pick up a neighbouring field.
2. **`--subset-field` was declared and never read.** It defaulted to a row-level `subset` field that
   does not exist on either dataset, and `_analyse` strata-fied only on `answer_type` /
   `answerable` / `dimension`, so the per-subset breakdown D142 asks for collapsed silently into a
   single `dimension=None` bucket. The subset is in fact inside the scorer's own output
   (`score.split` for RefSpatial, `score.subset` for RealWorldQA), which is the better source
   because the stratum and the number it strata-fies then come from one place. The compare now also
   **raises** if the two tiers disagree on a question's subset.

A declared flag that is never read is the same defect class as a write-only field: present, typed,
documented, and carrying no causal link. The first defect announces itself with an exception; the
second would have produced a complete-looking output with the required breakdown missing.

The hardcoded `study="StudySS1"` label was also wrong on an SS2 output and is now read from the
data files.

## 11. Why-analysis: where the cloud-minus-device gain comes from (A6000, 2026-11-20, user request)

OFFLINE. Committed per-question rows only, CPU on flash, no model, no GPU, no re-scoring. Script
`experiments/casestudy/ss2_why.py`, output `results/casestudy/study_ss2/ss2_why.json`. The three
questions asked are failure types per subset, image-clustered CIs, and the gain restricted to
well-formed answers. **No verdict: D136's gate call is the user's and is not made here, including by
implication.**

### 11.1 The headline result, and the stratum it hides

| dataset / stratum | n | device | cloud | delta | CI, question bootstrap | CI, image-clustered |
|---|---|---|---|---|---|---|
| RealWorldQA, mcq | 438 | 0.6370 | 0.7146 | **+0.0776** | [+0.032, +0.121] | [+0.032, +0.123] |
| RealWorldQA, free_form | 327 | 0.6789 | 0.7095 | +0.0306 | **[-0.021, +0.083]** | **[-0.018, +0.080]** |
| RefSpatial, location | 100 | 0.3350 | 0.5133 | **+0.1783** | [+0.072, +0.285] | [+0.056, +0.302] |
| RefSpatial, placement | 100 | 0.2300 | 0.2856 | +0.0556 | **[-0.050, +0.161]** | **[-0.056, +0.165]** |
| RefSpatial, unseen | 77 | 0.1688 | 0.2987 | **+0.1299** | [+0.026, +0.234] | [+0.015, +0.236] |
| RefSpatial, all | 277 | 0.2509 | 0.3714 | **+0.1205** | [+0.058, +0.184] | [+0.041, +0.202] |

**Two of the five strata do not resolve.** RealWorldQA's pooled +0.0575 is carried entirely by its
multiple-choice half: the free-form half is +0.0306 with a CI spanning zero under both resampling
units. RefSpatial's placement split is +0.0556, also spanning zero. The pooled figures are not wrong,
but a reader who takes them as "the cloud beats the device on these datasets" is reading a result that
holds on three of five strata and is unresolved on two.

### 11.2 Image-clustered CIs: immaterial on one dataset, material on the other

The committed CI resamples questions. Questions sharing an image are not independent, so that CI is
too narrow wherever images are reused. Clustering is by the manifest's `image_sha16`, the hash of the
decoded pixels, which is the same key the shared-image exclusion uses.

| dataset | questions | distinct images | questions per image | effect on the CI |
|---|---|---|---|---|
| RealWorldQA | 765 | 762 | 759 images with 1, 3 with 2 | **none to three decimal places** |
| RefSpatial | 277 | 97 | 1 to 10, median 3 | **the all-splits CI widens from [+0.058, +0.184] to [+0.041, +0.202]**, about 20 percent |

So the committed RealWorldQA CI needs no correction, and the RefSpatial CI does. It still excludes zero
after clustering, and the per-split CIs widen in the same direction without changing any sign. This is
worth stating as a check that passed rather than a problem found, but RefSpatial's clustering is heavy
enough (up to 10 questions on one image) that any future RefSpatial interval should be clustered by
default.

### 11.3 Failure types, and the answer to the well-formedness question

**RealWorldQA: formatting plays no part at all.** Every one of the 765 answers on BOTH tiers is a
well-formed candidate answer: 438 of 438 mcq rows yielded exactly one extracted letter on each tier,
and all 327 free-form replies are at most four words and none ran into the 16-token generation cap.
There are **zero** malformed answers on either side, so the gain restricted to well-formed-both IS the
headline unchanged, and no part of it is answer formatting. That was the thing most worth ruling out,
because the metric is exact string equality and CLAUDE.md's consistency check 3 records a case where an
accuracy column ranked arms backwards for exactly this reason.

| RealWorldQA failure type | device | cloud |
|---|---|---|
| mcq correct | 279 | 313 |
| mcq wrong letter | 159 | 125 |
| mcq no letter extracted | **0** | **0** |
| free_form correct | 222 | 232 |
| free_form yes/no flipped | 44 | 40 |
| free_form numeric off by one | 28 | 29 |
| free_form numeric wrong | 19 | 14 |
| free_form direction flipped | 2 | 2 |
| free_form contains the gold as a substring | 1 | 0 |
| free_form other wrong | 11 | 10 |

The two tiers make the SAME KINDS of mistakes at nearly the same rates on free-form: yes/no flips 44
against 40, off-by-one counts 28 against 29. The cloud's free-form advantage is 10 extra exact matches
out of 327, which is the +0.0306 that does not resolve. Its mcq advantage is 34 letters.

**RefSpatial: every formatting artifact penalises the CLOUD, so the gain there is understated.** The
device emits exactly one point on 275 of 277 questions; the cloud emits one on 260, zero on 9, and
three, five, eight or nine points on the remaining 8.

| RefSpatial failure type | device | cloud |
|---|---|---|
| all points inside the mask | 69 | 102 |
| points outside the mask | 206 | 164 |
| some points inside, diluted by extras | 1 | 2 |
| refused or gave no coordinates | 1 | 5 |
| **parser dropped a well-formed point** | **0** | **4** |

Two distinct mechanisms, both against the cloud:

1. **A parser gap the cloud hits and the device never does.**
   `ss2_bench_kit._iter_json_points` accepts a coordinate only as a 2-element numeric list under a
   point key, or as a bare 2-element list. It does **not** handle `{"x": .., "y": ..}`, and the two
   text fallbacks need brackets or parentheses that this form does not carry. The 32B prefers exactly
   that form, so four clean replies such as
   `{"points": [{"x": 234, "y": 357}]}` parsed to zero points and scored 0. **Register: this bounds
   the cloud's understatement at 4 of 277, or 1.44 pp, and it is a CONSTRUCTED BOUND, not a
   measurement.** The ground-truth masks are not on this box, the run having read them from
   `/dev/shm/ss2_data` on the Orin, so whether each dropped point lands inside its mask cannot be
   checked here; the true correction is between 0 and that bound. A fifth cloud reply carried
   coordinates in malformed JSON and is not counted in the four.
2. **Multi-point dilution**, which turns out to be small. The metric is the fraction of predicted
   points inside the mask, so a reply with one correct point and seven extras scores 0.125. Replacing
   it with "did ANY predicted point land inside the mask", which is derivable from the committed
   per-question accuracy without any mask, moves the all-splits delta from +0.1205 to +0.1227. Worth
   **+0.0022**, so the cloud's extra points cost it almost nothing.

**The gain on well-formed answers only**, defined for RefSpatial as both tiers emitting exactly one
parseable point:

| stratum | n well-formed both | device | cloud | delta | against the full-set delta |
|---|---|---|---|---|---|
| RefSpatial all | 258 of 277 | 0.2442 | 0.3915 | **+0.1473** [+0.085, +0.213] | +0.1205 |
| RefSpatial location | 94 of 100 | 0.3191 | 0.5319 | +0.2128 [+0.106, +0.319] | +0.1783 |
| RefSpatial placement | 92 of 100 | 0.2174 | 0.3043 | +0.0870 [-0.022, +0.196] | +0.0556 |
| RefSpatial unseen | 72 of 77 | 0.1806 | 0.3194 | +0.1389 [+0.028, +0.250] | +0.1299 |
| RealWorldQA, both subsets | all | unchanged | unchanged | unchanged | nothing to restrict |

So restricting to well-formed answers **raises** the cloud's RefSpatial lead by 2.7 points, from
+0.1205 to +0.1473, and placement still does not resolve even then. The direction is the useful part:
on both datasets, formatting either plays no role or works against the cloud, and on neither does it
inflate the gain. The one thing a why-analysis most needed to exclude is excluded.

### 11.4 The parser fix, proven at the parse level; the rescore is pending

Implementation fix applied on user instruction, 2026-11-20. `ss2_bench_kit._iter_json_points` now
accepts an `{"x": .., "y": ..}` object as a coordinate, which is the form the 32B prefers and the only
well-formed form the old parser missed.

**A survey first, so the fix covers what the models actually emit rather than the one case that was
noticed.** Over all 554 committed RefSpatial replies from both tiers:

| coordinate form in the reply | device | cloud | parsed before the fix? |
|---|---|---|---|
| bare `[x, y]` pair | 276 | 261 | yes |
| `(x, y)` parenthesised tuple | 0 | 7 | yes, by the third fallback |
| `{"x": .., "y": ..}` object | 0 | **5** | **no** |
| no coordinate form at all (a refusal) | 1 | 4 | n/a, correctly zero points |

**The proof** (`ss2_parser_fix_proof.py`, output `ss2_parser_fix_proof.json`) re-parses every reply
with the pre-fix parser read out of git at `066b575` and with the fixed one: **550 of 554 replies are
unchanged and exactly 4 change**, all of them cloud, each from 0 points to 1, all four with a
committed accuracy of 0.0. No device reply moves, so the fix cannot flatter the device, and no reply
that already parsed is disturbed.

| qid | split | parsed point after the fix | committed accuracy |
|---|---|---|---|
| `refspatial/location/18` | location | (112, 228) | 0.0 |
| `refspatial/placement/30` | placement | (374, 185) | 0.0 |
| `refspatial/placement/35` | placement | (164, 448) | 0.0 |
| `refspatial/unseen/36` | unseen | (374, 185) | 0.0 |

**One reply is deliberately NOT recovered.** A fifth cloud reply carries x and y inside malformed
JSON, `[{"x": 280, 840], "y": 840}]`. The instruction is to parse well-formed forms, and a regex loose
enough to salvage that would also salvage text that is not a coordinate, so it stays unparsed and is
listed in the proof rather than quietly fixed.

**What is NOT yet done, and why it is not done here.** The scores are unchanged: rescoring needs the
ground-truth binary masks, which are not on this box. Staging them elsewhere would not be as good as
rescoring where they already are, and for a reason worth recording on its own: **the manifest holds
`image_sha16` but no mask hash**, so a re-staged mask cannot be proven byte-identical to the one the
committed run scored against, while the mask is an input to every score. The rescore therefore belongs
on the Orin, which holds the originals, and it should record a mask sha256 as it goes so that this gap
closes for good. It is queued behind StudySH-EP rather than interrupting it.

**Until then every number in sections 11.1 to 11.3 stands as committed and is labelled pre-fix.** The
direction of the pending correction is known even though its size is not: at most 4 of 277 questions,
1.44 pp, and it can only move the cloud up, so the RefSpatial gain of +0.1205 is a floor and the
well-formed-only +0.1473 is unaffected (those four replies emit exactly one point, so they already
enter the well-formed subset, where they currently score 0).

## 12. Live arms that read a device score when deciding (same request; live2 audit)

Filed here because it was asked with section 11. Static read of committed code, re-runnable as
`experiments/orchestration/live2/device_score_audit.py`, output
`results/orchestration/live2/device_score_audit.json`.

This is the port rule applied to a CHANNEL instead of to an arm. An arm that escalates when the device
is unsure cannot make that decision if no device score reaches it, so the question is not whether the
channel is declared but whether it is supplied and read.

**Five arms declare `reads_device_answer = True`, and every one of them reads
`device_answer_confidence` in its own code:**

| arm file | where it reads the field |
|---|---|
| `cascade_adapted.py`, registered as `confidence-cascade` | lines 20, 89 |
| `cascade_routing_adapted.py`, registered as `cascade-routing` | line 121 |
| `r3streaming_adapted.py`, registered as **`r3-streaming`** | lines 56, 57 |
| `streamscout_adapted.py`, registered as `streamscout` | line 87 |
| `thinking_qwenvl_adapted.py`, registered as **`thinking-qwenvl-atdm`** | lines 62, 63 |

The two bolded registry names are not their file stems, and getting that wrong produced the
correction in 12.3.

No arm declares it False explicitly; `hybrid_llm_adapted.py` records in a comment that it stays False.

**In live2 the channel is supplied to none of them, and the break is in three independent places.**

1. `cstate.observation` (`cstate.py:486-541`) hard-codes `device_answer_confidence=None` on every
   `RecallQuery` it builds. It is the only assignment, and it is unconditional.
2. That function accepts a `reads_device_answer` parameter and uses it **0 times in its body**,
   confirmed by walking the function's AST rather than by eye.
3. `coordinator.py:243` calls `self.st.observation(t, epoch ...)` with two positional arguments and
   never passes the flag, so it always takes its default `False`. The parameter could not have
   mattered even if the body had read it.

**And the declaration is charged anyway, which is the part that matters.** `coordinator.py:171`
computes `self.reads_device` from the arm's declaration, and the two places that read it are both
costs:

- `coordinator.py:464` serves the opportunity at `o.t_event + DEVICE_ANSWER_CHARGE_S` instead of at
  `t_event`;
- `coordinator.py:498` forbids the arm from acting before `t_event + DEVICE_ANSWER_CHARGE_S`.

So an arm declaring that it reads the device answer **waits StudyD8's 0.567 s for an answer it is then
handed as `None`**. It pays the full price of the read and receives nothing, which leaves it strictly
worse off than the same arm declaring False. In CLAUDE.md's terms this is the write-only field
inverted: the flag is live, instrumented and consequential, and the only link it completes is the cost
one. It is also the shape check 7 names, a comparator charged one price while planning at another.

StudySIM1D already recorded the downstream consequence for one of the five, as PROPOSED and not
applied: with `conf is None`, streamscout's stage-0 branch fires and the query never reaches the
cloud, so all its recall decisions stay on the device. The same null holds in live2 for the same
reason.

**What this does not say.** It does not say these five arms are broken as published; their own code
reads the field correctly and the channel is real in the interface and in `experiments/orchestration/live/`
(`adapter.py:201`). It says that **in live2** the device-score channel is unexercised, so any live2
result in which one of these five arms declines to escalate is an ABSENT LINK under Rule 2 and not
evidence about cascading. Supplying the field is a methodological change and needs a ruling: the value
exists in committed form (StudyE7 Job A per-question `letter_probs` for the 4B-D2 configuration, 839 of
845 questions, per StudyB-baselines amendment 2), so it is a wiring decision and not a measurement
problem.

### 12.1 Fixed, and proved on dry cells (user ruling, 2026-11-20)

All three break points are closed. `cstate.observation` now populates the field from the committed
table when `reads_device_answer` is true, it uses that parameter, and `coordinator.py` passes it. The
value is `baselines/device_confidence.py` and nothing else, which is StudyE7 Job A's per-question
`letter_probs` mass on the letter the 4B actually emitted, the harness's own DEVICE answer
configuration. Nothing is synthesized.

**Two failure modes are kept apart on purpose, because conflating them is the defect being fixed.** A
TABLE that cannot be loaded now RAISES, because returning None there would reproduce the silent
absence this fix exists to remove. A QUESTION absent from the table returns None and is counted:
single-shot questions have no committed answer probability at all (12.2), so None is the honest value
for them and every arm already handles it.

**The proof** (`device_conf_wiring_proof.py`, output `device_conf_wiring_proof.json`), on the frozen
grid's own cell: seed 4, 16 devices, 1,200 s, 40:40:20, LH-REQ robots, SS2 pool, dry engine. Pre-fix
digests are the committed `baseline_prescreen.json` (a592e51) on the identical cell, so the comparison
is against a committed artifact rather than against a rerun.

All five declaring arms are covered. An earlier version of this proof ran only three, because its arm
list used file stems for two of them and they raised "unknown arm", which I then misrecorded as those
arms being unregistered (12.3).

| arm | confidence present / absent | declines on high confidence | escalates on low | digest | committed pre-fix digest |
|---|---|---|---|---|---|
| `confidence-cascade` | 20 / 357 | **13** | 7 | `7bbf9555d68e6f29` | `7212c388684ed51d` |
| `cascade-routing` | 20 / 357 | **20** | 0 | `9a18cc1be9aa65c6` | `6fee784e54567912` |
| `r3-streaming` | 24 / 357 | **19** | 0 | `8aecd24ed0980871` | `c66adcf4ddc672a7` |
| `streamscout` | 20 / 357 | **0** | 20 | `e6345d256e07f6ba` | `7212c388684ed51d` |
| `thinking-qwenvl-atdm` | 47 / 357 | **0** | 17 | `94f91d4ebb30b5d3` | `7c4a2c3459039bb1` |
| `b7-edf-feasibility` (control) | 0 / 377 | 0 | 0 | `67c8da3057a09aff` | `67c8da3057a09aff` |

The "present" column counts recall DECISIONS carrying a confidence, not distinct questions, which is
why two arms exceed the cell's 20 robot questions: an arm that re-decides a query across epochs reads
the value more than once. The denominator 357 is the single-shot questions, which have no committed
probability at all until 12.4's re-record.

Four things that table settles.

1. **The field arrives**, counted at the point of USE inside each arm's own `decide` rather than from
   a coordinator counter. That is the stronger read: a counter proves the supplier ran, this proves
   the value reached the code that consumes it.
2. **The characteristic decision fires for three of the five.** `confidence-cascade` declines to
   escalate 13 times and escalates 7, so both branches of its confidence test are reached;
   `cascade-routing` declines 20 times and `r3-streaming` 19. **`streamscout` and
   `thinking-qwenvl-atdm` escalate every time and never decline**, so the specific
   decline-on-high-confidence decision does NOT fire for them in this cell. That is their own fitted
   thresholds acting on these confidences rather than a wiring failure, since the field demonstrably
   arrives and their digests demonstrably move, and it is reported as a shortfall against the
   requested proof instead of being rounded up to a pass. Whether those thresholds are right at these
   confidences is a question about those arms, not about the wiring.
3. **The switch reaches a decision** (Step 2b): every treated arm's digest differs from its committed
   pre-fix digest. The sharpest evidence is what the fix SEPARATES. Pre-fix, `confidence-cascade` and
   `streamscout` had the **same** digest, `7212c388684ed51d`, because neither received a confidence and
   both collapsed to the same decisions. They are now distinct, so two arms that were
   indistinguishable are distinguishable.
4. **The control is byte-identical.** `b7-edf-feasibility` declares nothing and its digest is exactly
   its committed pre-fix digest. That matters beyond tidiness: b7 is the background arm StudySH-EP's
   cost-under-load cell runs, so a change there would have meant the fix perturbed work in flight.

**Coverage is a workload fact, not a supplier weakness.** 20 of 377 looks thin because in that cell
only 20 recall questions are robot questions while 357 are single-shot. The same arm on a robot-only
two-type cell (50:50, LH-REQ, 16 devices, 1,200 s) gets **24 of 24, full coverage**, with confidences
spanning 0.387 to 1.0 and decisions splitting 16 DEVICE to 8 CLOUD.

**A checker failure worth recording, because it produced an impossible result.** The first version of
this proof computed its own decision digest from `r["action"]` and `r["key"]`, which are not fields of
a decision row, so every row hashed to the same string and the digest became a function of row COUNT
alone. Three different arms collided on one digest and b7 appeared to change. b7 reads no confidence
and cannot change, so that impossible failure was the checker breaking rather than the fix, exactly as
CLAUDE.md check 7 warns. The proof now imports the committed `baseline_prescreen._digests` instead of
reimplementing it.

**Earlier runs are labelled, not altered.** Five committed live2 run directories predate the fix and
each now carries a `DEVICE_CONFIDENCE_NOT_DELIVERED.md` marker, listed in
`results/orchestration/live2/device_conf_absent_link_runs.json`: four `confidence-cascade` pilot cells
and one `cascade-routing` cell. Nothing in them is deleted or recomputed; what is bounded is the
interpretation. `streamscout`, `r3-streaming` and `thinking-qwenvl-atdm` are all registered and have no live run, so
they never paid the charge and need no relabelling. **An earlier version of this paragraph said the
last two were not registered at all. That was wrong; see 12.3.**

### 12.2 Single-shot has no committed answer probability, and what a re-record needs

**Reported as asked: the Orin StudySS1 and StudySS2 runs did NOT record answer probabilities.**
`ss2_run.py` sends `temperature=0.0, seed=0, max_tokens, stream=True` and no `logprobs` field, so no
per-question probability exists for any single-shot item. The committed rows carry `answer`,
`answer_raw`, `completion_tokens`, `prompt_tokens`, `score`, `ttft_s` and `total_s`, and nothing
probabilistic. That is why 357 of 377 recall questions in the frozen grid's cell return None, and the
None is correct rather than missing.

What a re-record needs, split by whether it is a re-record or a design decision first:

| items | what is needed | re-record, or a ruling first? |
|---|---|---|
| RealWorldQA mcq, 438 of 765 | `logprobs: true, top_logprobs: 20` on the request, then the mass on the emitted letter over A to D. The exact analogue of StudyE7's `letter_probs`, needing no new definition | **pure re-record** |
| RealWorldQA free_form, 327 of 765 | there is no letter, so a confidence must be DEFINED: the sequence probability of the emitted answer, length-normalised or not | **ruling first**, then re-record |
| RefSpatial, all 277 | the answer is coordinates, neither a letter nor a short string, and no committed precedent exists for a point-answer confidence | **ruling first**, and the definition is the harder half |
| cost | 1,042 device items, one at a time, cold per image, on the Orin, same kit and prompts | adds `logprobs` to the request only. No prompt or image changes, so the answers themselves should reproduce the committed ones, and that equality is the control the re-record should report |

So the MCQ half can be supplied by adding one request field and re-running the device pass. The
free-form and point halves need a ruling on what a confidence MEANS for an answer that is not a
letter, and until then None for those items is the honest value and the arms handle it.

**One clarification about dashcams, since the instruction mentioned them.** Dashcam device scores are
already delivered and always were: `cstate.observation` builds each `EpisodicStream` with
`delivered_scores`, the device's own per-instant scores, so arms reading the episodic side have never
been starved. The gap was only ever on the recall side, which is where `device_answer_confidence`
lives. Nothing was added for dashcams because nothing was missing.

### 12.3 Registry reconciliation before the sweep resumes, and a correction of my own

User instruction 2026-11-20. Script `experiments/orchestration/live2/sweep_registry_recon.py`,
output `results/orchestration/live2/sweep_registry_recon.json`.

**The correction first, because it is mine.** 12.1 reported `r3streaming` and `thinking-qwenvl` as
"not in the live2 registry at all". Those are FILE STEMS, from `r3streaming_adapted.py` and
`thinking_qwenvl_adapted.py`. The registry names are **`r3-streaming`** and
**`thinking-qwenvl-atdm`**, and both are registered and both declare `reads_device_answer`. My audit
asked the registry for names I had guessed from file names, got "unknown arm", and recorded the
answer as a fact about the registry. **All five declaring arms are live2-registered, not three**, and
the wiring proof now covers five.

A second way the same mistake was available: `arms.ARMS` alone is not the registry. Importing
`hybrid` adds the hybrid configs, so `hybrid-F-lhreq`, which is in the sweep list and has 7 live
runs, is absent from that dict until the import the driver performs. Membership is therefore settled
by calling **`make_arm`**, the driver's own construction path, and never by a name lookup. That is the
rule this script enforces, and it is the same lesson Step 2b states for a switch, applied to a name.

**The sweep list is sound.** All **29** names build through `make_arm`; **0** are unbuildable. So the
sweep can neither fail on a name nor silently run the wrong arm.

| sweep name | registered and buildable | declares `reads_device_answer` | live run dirs |
|---|---|---|---|
| `r3-streaming` | yes | **yes** | **0** |
| `streamscout` | yes | **yes** | **0** |
| `thinking-qwenvl-atdm` | yes | **yes** | **0** |
| `cascade-routing` | yes | **yes** | 1 |
| `b7-edf-feasibility` | yes | no | 12 |
| `eco-llm` | yes | no | 15 |
| `mooncake` | yes | no | 8 |
| `attentionstore` | yes | no | 7 |
| `hybrid-F-lhreq` | yes | no | 7 |
| `hybrid-llm` | yes | no | 4 |
| `b9`, `kvflow`, `utility-per-cost` | yes | no | 1 each |
| the remaining 16 names | yes | no | 0 |

The full per-name record is in the JSON; `confidence-cascade` is **not** in the sweep list, which is
why it appears in the wiring proof but not here.

**What this means for the sweep, and it is good news.** Four sweep arms read device confidence, and
three of those four have never run live at all, so the sweep will be their first live run AND their
first with the field delivered. Only `cascade-routing` has a prior live cell, and that one cell is
labelled under 12.1. So no post-fix sweep cell will have to be compared against a pre-fix twin for
three of the four, and for the fourth the pre-fix cell is already marked as an absent link.

### 12.4 The single-shot re-record: kit landed, run pending on the Orin

User ruling 2026-11-20. The kit is committed and runs on the Orin after StudySH-EP; no values exist
until it does, and `device_confidence` returns None for single-shot questions until then, which is
the honest value rather than a gap.

| piece | what it does |
|---|---|
| `ss2_run.py --logprobs` | adds `logprobs: true, top_logprobs: 20` to the request and records the per-token top-20. **Off by default**, so the function that produced the committed answers is unchanged. Nothing else moves: same prompt, same image, same greedy decoding and seed, so the ANSWERS must reproduce the committed ones and that equality is the re-record's own control |
| `ss2_device_confidence.py` | turns a re-recorded run into the per-question table |
| `device_confidence.py` | now merges that table beside the robot one, with `source_of()` naming which table a value came from. The two key spaces are disjoint, a 64-hex digest against `<dataset>/<id>`, so neither can mask the other |
| `ss2_refspatial_rescore.py` | the same Orin pass does the 11.4 rescore with the fixed parser, **recording a sha256 per mask**, which the manifest has never had |

**The confidence rule, as ruled**, and why the mcq half is deliberately not a new definition:

| items | rule | strength |
|---|---|---|
| mcq | the committed `study_f_common.letter_probs`, mass on the letter the model actually emitted, lifted by AST and not retyped | primary. This is **exactly** what StudyE7 supplies for robot questions, so the two sources feeding `device_answer_confidence` are the same quantity rather than two notions of confidence sharing one name |
| free_form | geometric mean token probability, `exp(mean(token logprob))` | primary |
| RefSpatial points | the same rule as free_form | **weak, and labelled so in every row.** Token confidence in the digits of a coordinate is not confidence that the point is right |

Length is why the two rules differ at all. A letter is one token, so its probability IS the answer's
probability. A free-form answer is several tokens and a product over them falls with length, which
would make a long correct answer look less confident than a short wrong one; the geometric mean
removes that dependence.

**Two controls the Orin pass must report**, both of which can fail and neither of which is optional:
the re-recorded answers must equal the committed ones question for question, since only `logprobs`
was added; and the rescore must move **zero device rows**, because the parser fix adds a form no
device reply used. `ss2_refspatial_rescore.py` exits non-zero if a device row moves.

Once the table exists, the wiring needs no further change: `cstate._device_confidence` looks the
question id up in `device_confidence.confidence`, which now consults both tables, so single-shot
confidences reach the arms by the same path as robot ones. The per-arm proof is then re-run with
`device_conf_wiring_proof.py`, where the coverage line should move from 20 of 377 toward full, and
that is the number to check rather than taking the wiring on trust twice.
