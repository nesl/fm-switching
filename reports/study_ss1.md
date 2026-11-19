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
