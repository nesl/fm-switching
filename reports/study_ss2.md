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
