# StudyLIVE2-fleet: devices, data and the offline scorer for live round 1

**STATUS: RESUMED AND COMPLETE FOR THE FLASH SCOPE.** Part 1 was reported first under a stop
condition (no E-id, no committed design log); the four blocking conditions are now closed, three
by the user's rulings (design log D81 to D94, committed 2026-11-17 under D92) and one by the
pre-registration row `StudyLIVE2-fleet` in `research/EXPERIMENTS.md`. Parts 3 to 6 are built and
their flash tests pass. **Part 2 is written and deliberately NOT RUN**, because the frames are
not on this box; ruling D91 says it runs on the host that holds them.

Host: `nesl-Z790-CLASSIFIED` (flash). CPU only. No GPU, no H100, no model, no network.
Repository: `/home/pragya/Desktop/FM-switching` at `31ede80`. Part 1 written 2026-11-18; parts 2
to 6 added 2026-11-17 (the dates are the session clocks and are left as recorded).

**AMENDED TWICE, 2026-11-17, for D95, D96 and D97.** Amendment 2 is section 15.

**AMENDED 2026-11-17 for D95 and D96.** The user ruled on open issues 1 and 2 of this report and
the rulings are committed as design log rows D95 (pilot design) and D96 (live harness ids and
digest). D96 adopted this session's digest definition as canonical and settled the
opportunity-id conflict in favour of generator-assigned ids. Sections 4, 5, 7.3, 8, 9, 10, 13 and
14 are amended; the amendment is bounded to those two rulings and nothing else in this report
changed.

**NOTHING IN THIS REPORT IS A MEASUREMENT.** Every run in parts 4 and 6 used the stub
coordinator, which holds no model, and every scoring run used the committed INTERIM calibration
map, which D86 permits for flash tests and nothing else. Every number below is either a value
read from a committed artefact (with its path and sha256), arithmetic over such values (labelled
DERIVED), or a property of the harness itself (scheduling lateness, emulator CPU), which is a
statement about this box and not about the system under study.

---

## 0. The four Part-1 blocking conditions, and how they closed

| id | Part-1 blocker | closed by |
|---|---|---|
| **B1** | no `StudyLIVE2-fleet` row in `research/EXPERIMENTS.md`, and D62 to D80 existed only inside the task brief | the parent session committed `research/policy_design_log.md` (D1 to D94), `research/policy_spec_v4.md` and `research/policy_ablations.md` to the repository under **D92**, and added the pre-registration row. Every design citation in this report now points at a committed file, not at a prompt. |
| **B2** | D71's robot minimum of 20 questions PER DEVICE is unreachable: 0 of 164 EVAL sessions holds 20, the maximum is 6 and the median 4, at any run length | **D82**: the robot target is POOLED over all robot devices in a run, p = 90 %, L = 5 s, minimum 20 questions per RUN. A run whose pool holds fewer than 20 is marked ineligible for the robot part and reported. The worst-served robot device and the per-device distribution are always reported. **D83** additionally lets a robot device CHAIN sessions, so a 10-minute run is not spent inside one 300-s session. |
| **B3** | the round-1 frames are not on this box, so Part 2 cannot run here; and the E10a JPEG outputs were never stored, so there is nothing to diff against | **D91**: encoding runs on the host that holds the frames, with the recovered E10a recipe, recording the Pillow and libjpeg versions in the manifest; the check is against E10a's committed byte quartiles and per-request base64 sizes, and byte-exactness to E10a is NOT claimed. The two scripts are written here (section 6) and were not executed. |
| **B4** | streaming AP over the committed 300-clip set is not computable at the smaller cells | **D85**: dashcam task value is streaming AP over the clip-PLAYS completed in the run, plays cut by the run end excluded for every arm, indexed by play id, paired across arms, pooled across seeds, and labelled "not comparable to the committed 300-clip AP". **D84** allows repeats across devices because caches are isolated per device, with repeat counts reported and repeats declared not independent samples. |

Section 1 below, written in Part 1 for contrast with B2, now has the ladder behind it: the
dashcam 200-instant minimum is met by every dashcam device in every cell measured in section 7,
including the 3-minute pilot.

---

## 1. What D71's dashcam minimum does look like, for contrast

This one is fine, and is recorded so the contrast with B2 is on the record. The StudyCTRL1c
decision instant is on the **0.5 s cadence** (section 2, item a), so a dashcam device offers 2
monitoring opportunities per second of clip time. Instants inside one clip run t = 3.0, 3.5, ...
up to the clip duration (StudyE9b `T0 = 3.0`), which is 70.3 instants per clip on average and
21,098 over the 300-clip set (DERIVED).

| | per dashcam device | D71 minimum | met |
|---|---|---|---|
| 180 s pilot | 360 instants | 200 | yes |
| 600 s main | 1,200 instants | 200 | yes |

200 instants is reached after about 103 s of clip time, so roughly 2.7 clips.

---

## 2. Part 1 provenance

Every path is absolute. sha256 is the full file digest, shown to 16 hex characters. "rows" is
lines for JSONL and JSONL.GZ, records for the derived sets.

### a. Nexar dashcam clips, the decision-instant cadence, and the streaming AP labels

| item | value | source |
|---|---|---|
| source dataset | HF `nexar-ai/nexar_collision_prediction` @ `7535d065`, 2,857 files, 31,379,033,414 B; train 1,500 videos (750 pos / 750 neg), 1280x720 H.264 | StudyD0-nexar, `reports/dashcam_data_check.md` |
| scope decision | train split only; test-public and test-private unused (timebase unresolved, finding F3); DoTA unused | same |
| SH-monitoring evaluation set | **300 clips**, 150 positive / 150 negative, all on the `val` side | StudyD14b, carried through CTRL1/1b/1c and E9b/E9c |
| clip durations | min 18.0 s, mean 37.87 s, median 40.12 s, max 60.0 s; 11,361 s of clip time in total (DERIVED) | `d14b_trace_h100nvl.jsonl.gz` |
| decision-instant cadence | **0.5 s** | StudyCTRL1c |
| score grid the AP is defined on | 0.25 s from t = 3.0 s | StudyE9b `STEP_DENSE`, `T0` |

Files:

| path | rows | bytes | sha256 |
|---|---|---|---|
| `/home/pragya/Desktop/FM-switching/results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz` | 168,056 (300 clips) | 4,320,544 | `6781ad8501ba2e6a` |
| `/home/pragya/Desktop/FM-switching/results/dashcam/ctrl1b/d14b_folds.json` (the 300 clip ids and the 5 folds) | 300 assignments | 11,889 | `47689a1d3828ac35` |
| `/home/pragya/Desktop/FM-switching/results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv` | 1,501 (1,500 clips + header) | 77,034 | `02691e28344112e3` |
| `/home/pragya/Desktop/FM-switching/results/dashcam/study_d14_trace/frames_sha256_manifest.jsonl.gz` | 86,180 | 4,427,615 | `6de6fca2f6e71c0b` |
| `/home/pragya/Desktop/FM-switching/results/dashcam/study_d14_trace/d14_requests_manifest.jsonl.gz` | 31,980 (10,660 each at N = 1 / 3 / 9) | 4,858,232 | `d36ddc988de52d88` |
| `/home/pragya/Desktop/FM-switching/results/dashcam/study_d14b/frames_sha256_manifest.jsonl.gz` | 45,614 | 2,342,565 | `fd155c40c008e6e6` |

The cadence quotes, verbatim from `reports/study_ctrl1c_calibrated.md`:

- line 80: "Carried forward UNCHANGED and declared rather than re-derived: the 5 folds ... **the
  0.5-s decision cadence**, every latency (device cadence 0.75 s and latency 0.567 s, cloud latency
  0.3950 s, uplink 13.6 Mbit/s, RTT 0.044 s)"
- line 843 (definition audit): "a \"turn\" as a **decision instant on the 0.5-s cadence**"
- line 625: "**The 0.5-s decision cadence is the binding constraint here, not the trigger design.**"

Three further cadences live in the same row and must not be confused with it: the device compute
cadence 0.75 s, the cloud call cadence 0.50 s, and the background trickle grid
{1, 2, 4, 5, 6, 8, 10} s. StudyD15's own AP is on a coarser 1 s grid (its 10,660 integer-second
instants), not the 0.25 s grid.

**The streaming AP labels: there is no label file, and no per-instant ground truth exists
anywhere.** The labels are per-clip (binary positive / negative) plus a per-clip `time_of_event`,
both carried inline on every row of `d14b_trace_h100nvl.jsonl.gz`, and the per-instant label is
derived by `study_e9b_dense.target_index`: for a positive clip exactly ONE instant is the positive
at each horizon (the grid point nearest `time_of_event - h` on the absolute grid, clamped), and
every instant of a negative clip is a negative. The bootstrap is a label-stratified clip resample,
NB = 2,000, seed 0. Known gaps carried from StudyD0: Nexar metadata has no collision versus
near-collision field (finding F1), so the label is binary only; and the clip-level label is used as
the calibration target, which CTRL1c already declares as a proxy in its own check 6.

### b. Orin device scores per Nexar instant, and the ORIN2 calibration map

| path | rows | bytes | sha256 |
|---|---|---|---|
| `/home/pragya/Desktop/FM-switching/results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz` | **42,014** over 300 clips | 1,557,804 | `38614bfc7b29cc19` |
| `/home/pragya/Desktop/FM-switching/results/device/study_d15/partA_scores.jsonl` | 10,660 over 300 clips | 8,581,210 | `7ada35e6cca82823` |
| `/home/pragya/Desktop/FM-switching/results/dashcam/study_orin2/orin2_d3dev_scores.jsonl.gz` | 6,010 over 601 clips (D3 DEV, the calibration fit set) | 222,146 | `d52d3d56648ac06f` |
| `/home/pragya/Desktop/FM-switching/results/dashcam/study_orin2/orin2_calibration.json` | the canonical `a`, `b` | 700 | `468148497d4c4e27` |

The 42,014 rows are every StudyD14b N = 1 request on the 0.25 s grid over the 300 clips, which is
the dense set a dashcam device needs; 10,660 of them carry a non-null `d14_request_id` and are the
integer-second StudyD15 overlap, on which the Orin reproduces StudyD15 at Pearson 1.000000, max
absolute difference 0.0. Per-row schema: `request_id, d14_request_id, file_name, clip, t, label,
time_of_event, duration_s, p_yes, score, first_token, yes_seen, no_seen, neither, prompt_tokens,
cache_n, ttft_s, total_s, clock_ok`, with `score = log P(Yes)` from the first token's top-20
Yes/(Yes+No) mass, floored at 1e-12, and `cache_prompt = false` on every request.
Stack: llama.cpp `c0fd786`, Qwen3-VL-4B-Instruct-F16 GGUF plus mmproj-F16, greedy, seed 0, one
request at a time, GPU clock pinned at 1,300,500,000 Hz with `clock_ok` true on every row.

**Calibration map.** `a = 0.114932`, `b = 1.174287`, recorded in `orin2_calibration.json`, in
`study_orin2_part1_analysis.json` (`orin_4b_map.a/.b`), in `reports/study_orin2_stack.md` lines 21,
90 and 269, and in `results/INDEX.md` line 859. Verbatim, `reports/study_orin2_stack.md` line 21:
"One Platt map fit for the Orin 4B: **a = 0.114932, b = 1.174287** (raw log P(Yes) at calibrated
p = 0.5 is -10.2173)."

It maps **from** the Orin 4B's raw per-instant score (`score` = log P(Yes) on the llama.cpp F16
stack) **to** a calibrated log-odds of the clip-level label, as `logodds = a * log(p_yes) + b`. Its
purpose is to put the device tier on the same scale as the cloud 32B tier so the two can be ranked
together (D57). The companion maps in the same file are H100 4B `a = 0.114603, b = 1.140751` and
**cloud H100 32B `a = 0.129472, b = 1.848187`**. Fit: sklearn `LogisticRegression(C=1.0, lbfgs)`,
seed 0, on the 6,010 D3 DEV N = 1 requests (601 clips x 10 event-anchored offsets) against the
clip-level label.

Caveats to carry into round 1: the map is fitted on an event-anchored 10-offset sample and not on a
dense whole-clip trajectory, and CTRL1c section 16.2 records the D3-fitted device slope as 3.007x
steeper than a D14b-DEV fit on 90 instants (+0.114603 versus +0.038113); the dense 42,014-row set
has no 32B counterpart, so the cross-tier residual is measurable only on the 6,010 D3 DEV rows; and
StudyD15's own verdict REJECTED the H100-for-Orin proxy as an exact numerical stand-in.

### c. Orin device latency per monitoring instant

Available **per instant**, not only as a distribution: every score row above carries `ttft_s` and
`total_s`. Percentiles computed directly from the committed files (DERIVED, not quoted):

| set | n | ttft_s p50 | p90 | p99 | min | max | total_s p50 | total_s p99 |
|---|---|---|---|---|---|---|---|---|
| StudyORIN1 dense | 42,014 | 0.4760 | 0.4819 | 0.4870 | 0.4525 | 0.5555 | 0.5312 | 0.5422 |
| StudyD15 Part A | 10,660 | 0.4784 | 0.4842 | 0.4876 | 0.4531 | 0.5494 | 0.5337 | 0.5428 |
| StudyORIN2 D3 DEV | 6,010 | 0.4708 | - | 0.4811 | - | - | 0.5260 | 0.5363 |

The distribution is very tight (p50 to p99 spread about 11 ms) because every monitoring instant is
a fixed-size 378-token single-frame cold request on a pinned clock. StudyD15 section A.6 states it:
"TTFT p50/p90/p99 = **0.479/0.484/0.488 s** - tight but *not* identical across requests (varies in
the 3rd decimal), as expected for a fixed-size single-frame request on a pinned clock". For round 1
the emulator should read the per-instant value from the recording rather than a constant, which
costs nothing and keeps the device answer and its latency on the same row.

### d. S-EMBER EVAL sessions

The EVAL split is not a data file: it is computed deterministically by
`experiments/orchestration/baselines/sember_split.py` (8,186 B, sha256 `699a1d7ec25e4907`) from
the StudyR1 input manifest, and its counts are committed in
`results/orchestration/study_b_baselines/amend2_sember_split.json` (2,246 B, sha256
`b6bd5dd666f6b107`). It was fixed by StudyB-baselines amendment 2 (2026-11-13): "DEV 70 videos /
243 questions (28.8%), EVAL 164 videos / 602 questions. **Overlap 0 questions, 0 videos.**", and
`experiments/orchestration/sim/workload.py:53` sets `QUESTION_SET = "EVAL"`.

| path | rows | bytes | sha256 |
|---|---|---|---|
| `/home/pragya/Desktop/FM-switching/results/sember/study_h/data/sember_mcq.jsonl` (questions, options, gold, question times) | 9,448 | 10,643,763 | `1ffa4321481e7f93` |
| `/home/pragya/Desktop/FM-switching/results/sember/study_h/data/sember_grounding.jsonl` | 9,448 | 11,062,463 | `fbd71e16f041e279` |
| `/home/pragya/Desktop/FM-switching/results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz` (question_id -> video_id, question_time, category) | 1,690 | 327,744 | `547d301c35c5f18b` |
| `/home/pragya/Desktop/FM-switching/results/orchestration/study_b_baselines/amend2_sember_split.json` | - | 2,246 | `b6bd5dd666f6b107` |

`sember_mcq.jsonl` is the only file carrying question text, options and gold together; a record
carries `question_time`, `options`, `correct_index`, `correct_letter`, `ground_truths`,
`answer_start_time`, `answer_end_time`, `duration`. Produced by StudyH2 from the gated
`facebook/S-EMBER`; its provenance block reads `"git_commit": "pre-provenance"`.

**Question times are real annotated timestamps, not synthesised.** `question_time` is a field of
the S-EMBER annotation. StudyH2 audited it: only 1 of 3,141 multi-question videos (0.03 %) has
identical `question_time` values, median spread 204 s, and its check SC5 passed with all 9,448
`memory_recency` values matching `qt - answer_start_time` within 1 s. The only synthesis anywhere
is the session convention (order by `question_time`, serve `video[0, question_time]`).

**EVAL session statistics, recomputed over all 164 sessions (DERIVED):**

| quantity | min | median | max |
|---|---|---|---|
| session duration | 300.0 s | 430.2 s | 1,200.0 s |
| questions per session | 2 | 4 | 6 |
| question rate | 0.15 q/min | 0.50 q/min | 1.20 q/min |

Total 602 questions over 164 sessions. **Sessions shorter than 10 minutes: 130 of 164 (79 %)**,
which is the D68 flag the brief asks for; none is shorter than 5 minutes (the minimum is exactly
300.0 s), 34 are at least 600 s, and only 3 are near 1,200 s. This is inherent to the dataset:
`reports/study_h_sember_structure.md` records that videos cluster at about 300 s (47.6 %) and about
600 s (17.8 % + 18.4 %). The questions also do not span the clip: the last question time sits at a
median 0.91 of the duration, and the distribution of questions per session is the table in B2.
`session_id` is the S-EMBER `video_id`, which encodes its own bounds as
`<uid>_start_<s>_end_<e>`, so duration is recoverable from the id itself.

Further scope notes: the 164 EVAL videos are a subset of StudyO's 234-video / 845-question pool,
which is itself not a random sample ("The 84 videos were not sampled at random ... chosen by greedy
set cover to fill the specific under-filled (category x distance_bin) strata"); `object_comparison`
is a reported band breach of the split; and the `le120` length bucket holds only 2 questions from
one video.

**The video and frame directories are MISSING on this box** (B3): StudyR1 records them off-repo on
the H100 host as `~/.cache/fm-switching/sember_videos` (30.2 GB),
`~/.cache/fm-switching/sember_frames` (11 GB) and `~/.cache/fm-switching/r1_inputs` (78 GB).

### e. Device RECENT-window answers on S-EMBER EVAL: AMBIGUOUS, two candidates, neither chosen

The brief anticipates that these came from the 4B on the H100 rather than the Orin and says to keep
them with a caveat. They did come from an H100 4B. But **two different committed answer sets both
answer to the description, they disagree, and nothing in the brief or the repository picks one**, so
this is reported as ambiguous rather than resolved. No substitution and no regeneration was done.

| candidate | what it literally is | file | rows | bytes | sha256 | committed accuracy |
|---|---|---|---|---|---|---|
| **(i) StudyE7 Job A, `4B-D2`** | the set the existing harness actually serves as the DEVICE recall answer; Qwen3-VL-4B-Instruct on h100nvl GPU 2 under vLLM 0.31.0 @`ebb281ec`, on StudyRH4's **D2** input (2 s stride images), **not a RECENT window** | `/home/pragya/Desktop/FM-switching/results/sember/study_e7/e7_requests_h100nvl.jsonl` | 945 lines; 602 distinct EVAL questions | 899,833 | `8774ff8e31007d64` | 30.9 % [27.8, 34.0] on the paired 839 pool |
| **(ii) StudyClean cell H1** | the literal **RECENT** window answered by the 4B; h100nvl GPU 1, vLLM 0.31.0, FA3, prefix caching off, greedy 512, on K3's exact 845 RECENT requests | `/home/pragya/Desktop/FM-switching/results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz` | 2,565 lines (SAN 30 / H1 845 / H2 845 / H3 845) | 195,699 | `c13e0af6385f98ac` | 32.54 % on all 845 |

The harness convention is explicit about (i) being the device proxy.
`experiments/orchestration/baselines/recall_profiles.py`: "**4B D2 is the DEVICE PROXY and is
labelled as such.** Its letters are the H100 4B's". `experiments/orchestration/sim/metrics.py`
carries the required caveat text already, as `DEVICE_PROXY_NOTE`: "StudyD15 Part A REJECTED the
H100-for-Orin proxy as an EXACT numerical stand-in, so every device recall number here is valid for
ORDERING and first-order value and is NOT an exact device number. StudyE8 Part D measured 68/68 warm
and 27/27 cold agreement on byte-identical inputs and StudyF4 measured 0.972-0.981 per-question
agreement, which is what makes the ordering usable." That caveat covers whichever set is chosen.

Two real-Orin (llama.cpp) answer sets exist and **neither is a RECENT window on EVAL**, so neither
is a candidate: `results/device/study_f4/partA_accuracy.jsonl` (2,535 rows, 2,262,420 B, sha256
`3b391bb53dc4f4c6`) is a last-3-second window and scores at or below the 20 % chance floor
(0.1538 / 0.1373 / 0.1515 at N = 1 / 3 / 9); and
`results/device/latency_sember_4bi_f16_F16.jsonl` (120 rows, 71,912 B, sha256 `1f04acdc8e49d332`)
IS Orin DEV-RECENT at 120 s and 34.2 % (41/120), but it is a 120-question stratified sample drawn
before the split existed, only 85 of its 120 questions fall in EVAL, and its own report labels the
accuracy "incidental ... included only as a sanity signal".

### f. Device recall latency for the RECENT window on the Orin

Both paths, 20 DEV questions per history size, TTFT p50 in seconds:

| path | 11k-token history | 28k-token history |
|---|---|---|
| in-process libllama + libmtmd harness (**the device cost**, D61) | **0.146** | **0.225** |
| llama.cpp OpenAI-API server, the re-send path | 1.416 | 3.433 |

Verbatim, `reports/study_orin2_stack.md`: "The harness warm-recall TTFT p50 is 0.146 s (11k) and
0.225 s (28k) versus the server path's 1.416 s and 3.433 s: ratios 9.7x and 15.2x." and "The
harness is the device warm-recall baseline for policy evaluation; the server path is an API
artifact (D61)." Decomposition rows: 11k = 124.9 ms prompt eval, 1285.2 ms server, 146.2 ms
harness; 28k = 188.1 ms, 3245.1 ms, 225.4 ms. The server numbers reproduce StudyORIN1 Part 3's
1.41 / 3.43 s.

| path | rows | bytes | sha256 |
|---|---|---|---|
| `/home/pragya/Desktop/FM-switching/results/cost/study_orin2/orin2_warm_recall.jsonl` | 40 | 28,650 | `d1554ec45ef686b9` |
| `/home/pragya/Desktop/FM-switching/results/cost/study_orin2/orin2_warm_recall_summary.json` | - | 7,900 | `375e363b411cf85c` |
| `/home/pragya/Desktop/FM-switching/results/cost/study_orin1/orin1_recall_latency.jsonl` (superseded server path) | 40 | 15,095 | `22b96fffdfcbd19e` |

Two corrections to the brief's framing of this item, reported rather than applied:

1. **"RECENT window" is not what was measured.** The ORIN2 histories are warm **D2** image
   histories at 11k and 28k tokens on one DEV video
   (`9902221866524366_start_0.0_end_1199.959`, 578 frames, 20 DEV questions). No source calls
   either size RECENT. A RECENT-120 s prompt is about 12,422 input tokens (median, StudyDeviceLatency),
   so 11k is the nearest size, but equating the two is an inference and not a committed definition.
   All 20 questions are DEV-split, so no EVAL latency exists on this path.
2. **Nothing in the repository labels the re-send path a "sensitivity value".** Both
   `reports/study_orin2_stack.md` and the `StudyORIN2-stack` row in `research/EXPERIMENTS.md` say
   the stronger and opposite thing: the server path is an API artifact and must not be used as the
   device cost. The 1.416 / 3.433 s figures are available if a sensitivity arm is wanted, but
   calling them one is a new decision, not a committed one. Also note the harness figure is already
   conservative (it includes about 16 to 24 ms of extra question-eval the server charges to its
   cache) and that warm recall is not free: the slope is 0.0322 ms per cached history position.

The ORIN2 equivalence gate behind these numbers is a declared post-hoc tolerance: 0.05 nats was
pre-registered and FAILED at 0.064 to 0.100, and 0.15 nats replaced it with the user's approval.
Its own report flags this as "a post-hoc tolerance change, labelled as such, not a pre-registered
pass".

### g. The E10a JPEG encoders

Library in every case: **PIL (Pillow) `Image.save(..., format="JPEG", quality=q)`**. No cv2, no
ffmpeg, no `optimize`, no `progressive`, no explicit `subsampling`, no `qtables`. Images are
brought to RGB and PIL then writes YCbCr with its defaults, which is 4:2:0 at these quality values
(stated in the E10a Job A docstring). **No resize happens inside the encode step** in either
dataset; resolution is fixed upstream.

Nexar, quality 90, from `experiments/cost/study_e10a_parity_vllm.py` lines 73 to 87:

```python
def jpeg_bytes(png_bytes, q):
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=q)
    return buf.getvalue()
```

Input is the stored SMALL PNG bytes, decoded then re-encoded, pixel grid unchanged at **768x432**
(StudyD14 SMALL frames, LANCZOS-resized lossless PNG, `experiments/dashcam/d14_prepare.py`).
Wire form: `data:image/jpeg;base64,<...>`, one image part per frame. The sweep
`experiments/cost/study_e10a_sizes.py` lines 41 to 63 covers q in {75, 85, 90, 95} and asserts
every frame is (768, 432).

S-EMBER, quality 88, from `experiments/cost/study_e10a_parity_vllm.py` lines 133 to 144:

```python
def jpeg_b64(fr, q=88):
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(fr.transpose(1, 2, 0))).save(buf, format="JPEG", quality=q)
    return base64.b64encode(buf.getvalue()).decode()
```

Input is the already-final-size frames from StudyR1's npz (CHW uint8, transposed to HWC), so
RECENT is 512x384 and RICH / D2 is 352x256. Wire form: ONE `data:video/jpeg;base64,` URL whose
per-frame base64 strings are **comma-joined**, which is part of the recipe. StudyE10a-full reuses
the same function (`experiments/cost/study_e10a_full_vllm.py:41`).

Do not confuse these with the upstream q88 frame cache: `experiments/sember/study_o_q4.py:127-128`
writes the 1 fps `~/.cache/fm-switching/sember_frames/<video_id>/NNNNN.jpg` cache at quality 88 as
well. That is the SOURCE Job A sampled from, and it is already lossy, so an S-EMBER "source" frame
is a q88 JPEG re-decoded, resized and re-encoded at q88.

**Pillow version: MISSING.** Neither `results/cost/study_e10/e10a_run_meta_h100nvl.json` nor
`e10a_sizes.json`'s `_provenance` records it. PIL's default subsampling and quantisation tables are
version-sensitive, so byte-exact reproduction needs the version pinned from the E10a venv
(`/home/pragya/.venvs/fm-switching-vllm` on the h100nvl host for Job B).

Committed byte statistics, the only available cross-check (B3), from
`results/cost/study_e10/e10a_sizes.json` (git `c4eebb1d`, n = 934):

| dataset and resolution | n frames | PNG re-encoded median | **JPEG target median** | ratio |
|---|---|---|---|---|
| Nexar 768x432 | 500 | 342,064.5 B | **q90: 63,897.5 B** (mean 63,318.97; p25 49,810.25, p75 75,682.25) | 0.18746 |
| S-EMBER RECENT 512x384 | 200 | 273,875 B | **q88: 45,420.5 B** (mean 46,820.8; p25 37,818.5, p75 58,014) | - |
| S-EMBER D2 352x256 | 180 | 138,838 B | **q88: 24,570 B** (mean 24,596.3) | - |
| S-EMBER RICH 352x256 | 200 | 139,656 B | q88: 24,872 B (mean 24,743.7) | - |

Per-request medians from `reports/study_e10a_jpeg.md` section 1: RECENT 33.41 MB PNG to 5.54 MB
q88 (0.166); RICH 34.91 to 6.20 MB (0.178); D2 16.11 to 2.85 MB (0.177).

---

## 3. What the link model costs, from the committed constants

Recorded here because it is arithmetic over committed constants and it bounds whether the emulator
is feasible at all. D75 fixes a uniform 13.6 Mbit/s uplink and 44 ms RTT, which is exactly the
committed pair of StudyE4, StudyE9/E9b and StudyCTRL1/1b/1c.

| quantity | value | basis |
|---|---|---|
| dashcam frame upload (q90 median 63,897.5 B) | 37.6 ms serialisation + 22 ms flight = **59.6 ms** | DERIVED |
| dashcam uplink utilisation at 2 frames/s | 1.02 Mbit/s = **7.5 %** of 13.6 | DERIVED |
| robot history batch (15 D2 frames at 24,570 B = 368,550 B) every 30 s | 216.8 ms serialisation + 22 ms flight; **98 kbit/s** = 0.7 % | DERIVED |
| pull message (mode B) | 22 ms | D75 |
| answer delivery, 300 B payload | 22.2 ms | DERIVED |

`upload_s(354902)` returns 0.230766 s, which reproduces the committed decomposition exactly:
StudyE9 records "354,902 B at 13.6 Mbit/s is 0.209 s" and adds RTT 0.044 s.

**The downlink rate has no committed value and is an ASSUMPTION, not a measurement.** The committed
cloud-latency convention charges the UPLOAD only ("RTT 0.044 s + 354,902 B at 13.6 Mbit/s + StudyD7b
TTFT 0.1422 s") and omits the answer payload entirely. Round 1 needs to charge it, so the module
extends the committed constant symmetrically at 13.6 Mbit/s and makes the choice inspectable:
`downlink_sensitivity_s(300)` gives 0.0244 / 0.0225 / 0.0222 / 0.0220 s at 1 / 5 / 13.6 / 100
Mbit/s, so the whole range of plausible rates moves a delivery by 2.4 ms against a 1.0 s dashcam
deadline. The choice cannot change an outcome, but it is flagged rather than buried. The one
committed measurement nearby is StudyE31b's Irish 5G downlink spread, p10/p50/p90 =
0.90 / 9.58 / 102.9 Mbit/s, which is a different setting (outdoor vehicular 5G) and is not used.

Load this implies on the coordinator at 64 devices in mode A, 50:50: 32 dashcam devices at 2
frames/s is 64 frames/s at 63,897.5 B = **4.1 MB/s** of request bodies. StudyRH6 measured the vLLM
API server serving about 72 to 76 MB/s of bodies before it collapses, so the ingestion side has
about 18x headroom at this fleet size. That is a feasibility note, not a result.

---


## 4. Which ruling went where

Every ruling is implemented at one named place, so a ruling can be checked against code rather
than against prose.

| ruling | where it is implemented | how it is tested |
|---|---|---|
| **D67** ratios 50:50, 75:25, 25:75; no device mixes datasets | `trace.RATIOS`, `trace._split_fleet`; dashcam devices only ever read Nexar and robot devices only ever read S-EMBER | test a5, a6 |
| **D68** robot questions at their REAL times; history in fixed 30-s batches with D2 token accounting; predictive upload off | `data_sources.eval_sessions` reads `question_time` from the committed annotation; `trace.generate_trace` emits `history_batch` every `HISTORY_BATCH_S`; `data_sources.d2_batch_tokens` / `d2_frames_in` | test e5, e6, e9, e10 |
| **D69** identical opportunity streams; mode A push, mode B offer plus pull | the trace holds OPPORTUNITIES and is byte-identical across modes; the emulator converts per mode and must reproduce the trace's fairness digest for that mode | test a4, a4b, b (4 arms) |
| **D95** pilot at 600 s, seed 0, and the measurability rule | the ladder of section 7.2 is the evidence D95 (1) and (2) adopt; the rule itself lives in `ANALYSIS_PLAN.md` sections 3 and 7, with the seed-dependence of the boundary reported there | section 7.3 |
| **D96 (1)** every opportunity carries a generator-ASSIGNED `opportunity_id`, echoed unchanged, never constructed | `trace.generate_trace` hands out flat `opp<n>` labels in the trace's canonical order after sorting; `events.FIELDS` carries the field on `monitor_offer`, `monitor_frame` and `recall_question`; `events.opportunity_id_of` now READS it; `emulator` puts it on the wire and the scorer keys on it | test s4, s4b, s4c, a7, a8, d14b |
| **D96 (2)** the canonical fairness digest, order-independent over sorted tuples, with pull-mode frames excluded | `trace.fairness_digest` and `trace._digest_tuple`; `emulator._sent_digest` calls the same function on what it actually presented | test a4b, a9, a10, a11, b |
| **D70 / D91** JPEG wire format, encoded once and stored, versions recorded | `data/encode_jpeg.py`, `data/build_manifest.py`; `SEMBER_JPEG_CAVEAT` in every scorer header | not run on flash (B3) |
| **D71** targets are inputs, swept, every setting reported | `scorer/score.py` takes L and p as GRIDS and emits one sweep row per cell; it never selects one | test d1 to d6 |
| **D75** uniform 13.6 Mbit/s up and down, 44 ms RTT, no outages, per-device configurable | `links.LinkSpec`, `upload_s`, `pull_s`, `deliver_s`, `UplinkQueue` | test c1 to c10 |
| **D79** seeds fix assignment, offsets and order identically for all arms | `trace.generate_trace` is deterministic in the seed alone given (n_devices, ratio, run_s, stagger_s); separate `random.Random` streams for clips, sessions and stagger so changing one does not move the others | test a1, a2, a3 |
| **D81** every cloud answer tagged WARM or COLD from its per-request cached tokens | `scorer.robot_value` reads `cache_path` from the request log and splits accuracy by it; `CACHE_PATH_CAVEAT` in every header | test d8, d9 |
| **D82** robot target POOLED, minimum 20 per run, worst device always reported | `scorer.attainment`: `robot_pool_*` fields, `robot_per_device`, `robot_worst_device`; an ineligible pool cannot satisfy the capacity conjunct | test d4, d5, d5b, d7 |
| **D83** chained EVAL sessions, history from zero, session_start / session_end, staggered first start | `trace.generate_trace` robot branch; the batch counter restarts per session play | test e2 to e7 |
| **D84** distinct first, repeat only when the pool is exhausted, own play id per play, repeat counts reported | `trace._deal`, `play_id`, `TraceStats.clip_repeats` / `session_repeats` | test d14, e8; section 7 ladder |
| **D85** play-indexed streaming AP, cut plays excluded for every arm, not comparable to the 300-clip AP | `scorer._ap_streams` skips `play_completed = false`; `scorer.dashcam_value` builds a PLAY-level context for StudyE9b's own engine | test d10, d11, d13 |
| **D86** maps are INPUT files; INTERIM may not score a measured run | `data_sources.calibration` derives the label conservatively WITHOUT editing the committed file; `scorer.check_calibration` refuses | test f1 to f7 |
| **D87** device answers = the StudyR1 4B-I x RECENT set restricted to EVAL; device recall cost = the ORIN2 in-process harness; the 0.567 s wait rule for arms that wait | `data_sources.device_recall_answers` (with a self-check against the committed headline), `device_recall_latency_s`, `DEVICE_WAIT_RULE_S`; `DEVICE_ANSWER_CAVEAT` in every header | section 11; test d12 |

Rulings 8 and 9 needed no code: ruling 8 (RECENT versus D2 latency is moot for scoring, because
the target is on-time CLOUD service and the device answer is the fallback) is recorded in section
13 item 4, and ruling 9 (symmetric 13.6 Mbit/s accepted with the sensitivity note) is already in
`links.py` and in section 3.

---

## 5. What was built

| file | what it is |
|---|---|
| `experiments/orchestration/live2/fleet/links.py` | the emulated access link (Part 1 module, unchanged): `upload_s`, `serialise_s`, `pull_s`, `deliver_s`, `downlink_sensitivity_s`, `LinkSpec`, and `UplinkQueue`, the one-uplink-per-device FIFO shared serially between frames and history batches, which records the queueing delay per transfer rather than hiding it inside the transfer time |
| `experiments/orchestration/live2/fleet/events.py` | the fleet side's copy of the wire spec. EXTENDED: `session_start` and `session_end` added per D83; `opportunity_id` added to the three opportunity events per D96 (1), with `opportunity_id_of()` now READING it rather than constructing one; `check_against_schema()` PASSES against subagent A's `live2/schema.py` with field lists identical on all nine events, and carries a `PENDING_D96` tolerance that would have reported A's mid-build state instead of raising, had its change not already landed |
| `experiments/orchestration/live2/fleet/data_sources.py` | every round-1 input path and committed constant in one place, with `MissingInput` raised rather than any fallback. EXTENDED with the ruling inputs: `eval_sessions()` (164 EVAL sessions, 602 questions, real question times), `device_recall_answers()` (D87, self-checking), `device_recall_latency_s()`, `orin_dense_scores()` (42,014 per-instant scores AND per-instant latency), `calibration()` with the INTERIM / FINAL label rule, and the four caveat texts |
| `experiments/orchestration/live2/fleet/trace.py` | **Part 3.** `generate_trace(seed, n_devices, ratio, run_s, mode)` and `write_trace`, producing `trace.jsonl`, `device_answers.jsonl` and `trace_meta.json` with a file sha256, the generator-assigned `opportunity_id` on every opportunity (D96 (1)), and `fairness_digest_A` / `fairness_digest_B` with the mode's own under `fairness_digest` (D96 (2)) |
| `experiments/orchestration/live2/fleet/emulator.py` | **Part 4.** `FleetEmulator` (real-time, wall-clock paced, per-device uplink queues, both upload modes, lateness logging, digest assertion) and `StubCoordinator`, the deterministic flash stand-in that holds no model |
| `experiments/orchestration/live2/scorer/score.py` | **Part 5.** standing answers, attainment, the target sweep, capacity, play-indexed AP through StudyE9b's own engine, robot accuracy split WARM / COLD, the device-only arm from recordings, paired bootstraps, and the D64 diagnostics |
| `experiments/orchestration/live2/data/encode_jpeg.py` | **Part 2, not run.** The recovered E10a recipe, both datasets, recording Pillow, libjpeg, the JPEG codec, NumPy, Python and platform in `encode_meta.json` |
| `experiments/orchestration/live2/data/build_manifest.py` | **Part 2, not run.** The manifest (frame_ref, path, bytes, sha256) plus the E10a distributional check, read live from `results/cost/study_e10/e10a_sizes.json`; exits non-zero on any flagged quartile |
| `experiments/orchestration/live2/fleet/tests/test_live2_fleet.py` | checks (a) to (f), 111 assertions |
| `experiments/orchestration/live2/fleet/tests/test_scale.py` | check (g), the 64-device real-time run in both modes |
| `results/orchestration/live2/ANALYSIS_PLAN.md` | the analysis plan, **DRAFT FOR USER APPROVAL** |

---

## 6. Part 2: written, NOT RUN (D91)

Still blocked on this box exactly as Part 1 reported: `/home/pragya/data` does not exist,
`~/.cache/fm-switching` does not exist, `/home/nesl` is permission denied. The two scripts are
written so they can be run unchanged on whichever host holds the frames, and they refuse to
start if the source directory is absent rather than inventing anything.

What they carry that would otherwise be got wrong:

- the Nexar recipe is `Image.open(...).convert("RGB")` then `save(format="JPEG", quality=90)` on
  the STORED SMALL PNG bytes, with the 768x432 grid asserted and **no resize in the encode step**;
- the S-EMBER recipe is `Image.fromarray(np.ascontiguousarray(fr.transpose(1, 2, 0)))` then
  `save(format="JPEG", quality=88)` on StudyR1's npz CHW uint8 frames, and the wire form is ONE
  `data:video/jpeg;base64,` URL whose per-frame base64 strings are **comma-joined**, which
  `--emit-request-sizes` reproduces so the per-request size can be checked;
- PIL only. No cv2, no ffmpeg, no `optimize`, no `progressive`, no explicit `subsampling`, no
  `qtables`;
- the versions that can move a byte are recorded in the manifest, because E10a recorded none and
  PIL's default chroma subsampling and quantisation tables are version-sensitive;
- the check is distributional, against `e10a_sizes.json` read live: for Nexar the `jpeg90`
  quartiles at 768x432 over 500 frames, for S-EMBER the `jpeg88` quartiles per
  (construction, resolution) and the per-construction `request_bytes` over 845 requests. A
  quartile more than 10 % away is FLAGGED and the script exits non-zero.

**Byte-exactness to E10a is not claimed and cannot be checked** (D91): every E10a encode went to
an in-memory `BytesIO` and was base64'd straight into a request body, so no output was stored.

---

## 7. Part 3: the trace generator, and the ladder it produces

A trace is a deterministic device SCRIPT, not a measurement. It is **mode-independent by
construction**: D69 defines fairness as identical opportunity streams, so the trace holds
opportunities and the emulator turns each one into the wire event its mode needs. The same trace
file therefore serves mode A and mode B, which makes the two modes comparable rather than merely
similar, and test a4 asserts the two digests are equal.

### 7.1 The one reading that had to be chosen, and why

D83 says "the first session starts at a staggered seeded offset" and Part 3 says dashcam clips
run "back to back at the CTRL1c cadence from a seeded offset". Both are implemented as an offset
in **run time**: a device registers at t = 0 and begins its first clip or session at
`start_t ~ U[0, stagger_s)`, seeded, with `stagger_s` defaulting to the 30-s history-batch period
so batch boundaries and instant phases are decorrelated across devices instead of fleet
synchronous. The alternative reading, starting part-way INTO the first clip or session, was
rejected because D83 states that a new session's history starts from zero, which a mid-session
join contradicts, and because D85 excludes "plays cut by the run end", which presupposes whole
plays. `stagger_s` is a parameter and its value is in every trace's metadata.

### 7.2 The ladder, seed 1, all three ratios, pilot and main run lengths

`results/orchestration/live2/fleet/trace_ladder_seed1.json`. "dash >= 200" is how many dashcam
devices clear D71's 200-instant minimum; "min inst" is the smallest per-device instant count;
"robot q" is the POOLED question count against D82's minimum of 20.

| ratio | run | devices | dash / robot | dash >= 200 | min inst | plays done / started | robot q | pool >= 20 | sessions completed | clip repeats |
|---|---|---|---|---|---|---|---|---|---|---|
| 50:50 | 180 s | 4 | 2 / 2 | 2 of 2 | 322 | 9 / 11 | 4 | **no** | 0 | 0 |
| 50:50 | 180 s | 8 | 4 / 4 | 4 of 4 | 291 | 16 / 20 | 5 | **no** | 0 | 0 |
| 50:50 | 180 s | 16 | 8 / 8 | 8 of 8 | 291 | 32 / 40 | 14 | **no** | 0 | 0 |
| 50:50 | 180 s | 32 | 16 / 16 | 16 of 16 | 278 | 59 / 75 | 29 | yes | 0 | 0 |
| 50:50 | 180 s | 64 | 32 / 32 | 32 of 32 | 273 | 126 / 158 | 50 | yes | 0 | 0 |
| 50:50 | 600 s | 4 | 2 / 2 | 2 of 2 | 1,106 | 30 / 32 | 8 | **no** | 1 | 0 |
| 50:50 | 600 s | 8 | 4 / 4 | 4 of 4 | 1,075 | 57 / 61 | 22 | yes | 2 | 0 |
| 50:50 | 600 s | 16 | 8 / 8 | 8 of 8 | 1,066 | 120 / 128 | 47 | yes | 6 | 0 |
| 50:50 | 600 s | 32 | 16 / 16 | 16 of 16 | 1,054 | 237 / 253 | 86 | yes | 12 | 0 |
| 50:50 | 600 s | 64 | 32 / 32 | 32 of 32 | 1,054 | 477 / 509 | 151 | yes | 22 | **209** |
| 75:25 | 180 s | 64 | 48 / 16 | 48 of 48 | 273 | 186 / 234 | 28 | yes | 0 | 0 |
| 75:25 | 180 s | 32 | 24 / 8 | 24 of 24 | 278 | 90 / 114 | 15 | **no** | 0 | 0 |
| 75:25 | 600 s | 16 | 12 / 4 | 12 of 12 | 1,053 | 180 / 192 | 21 | yes | 2 | 0 |
| 75:25 | 600 s | 32 | 24 / 8 | 24 of 24 | 1,058 | 355 / 379 | 48 | yes | 6 | **79** |
| 75:25 | 600 s | 64 | 48 / 16 | 48 of 48 | 1,053 | 711 / 759 | 88 | yes | 13 | **459** |
| 25:75 | 180 s | 16 | 4 / 12 | 4 of 4 | 291 | 16 / 20 | 20 | yes | 0 | 0 |
| 25:75 | 600 s | 8 | 2 / 6 | 2 of 2 | 1,106 | 30 / 32 | 33 | yes | 4 | 0 |
| 25:75 | 600 s | 64 | 16 / 48 | 16 of 16 | 1,054 | 237 / 253 | 232 | yes | 33 | 0 |

(The full 30-cell table is in the JSON; the rows above are every cell that changes an answer plus
the 50:50 ladder in full.)

### 7.3 Three consequences of the ladder that the round-1 matrix has to absorb

1. **D77's pilot ladder has no eligible robot pool at its three smallest sizes. ADOPTED BY
   D95.** The pilot as D77 wrote it is 50:50 at about 3 minutes over fleets 4, 8, 16, 32, 64. At
   4, 8 and 16 devices the pooled robot question count is 4, 5 and 14, all below D82's minimum of
   20, so those three cells are ineligible for the robot part and the capacity conjunct cannot be
   met in them for ANY arm. **D95 (1) amends D77: the pilot now runs at 600 s, the same as a main
   run, at seed 0.** **D95 (2)** adds the measurability rule: a fleet size enters the main sweep
   only if its robot pool reaches 20 questions at the main run length, a smaller size is reported
   "robot part not measurable" and never as a pass, and size 4 is kept only as a harness sanity
   check.

   One thing the ladder shows that D95 (2) does not yet fix, now recorded in `ANALYSIS_PLAN.md`
   section 3 as a CHOICE: **the entry point is seed-dependent at the boundary.** At 50:50 and
   600 s, 8 devices clears the bar at seed 1 (22 questions) and misses it at seed 0 (18); at
   75:25, 16 devices clears at seed 1 (21) and misses at seed 0 (17). That follows from D82
   evaluating per run on sessions holding 2 to 6 questions each, so near the bar the seed's deal
   decides eligibility. The pilot's own seed is 0, which puts its entry points at 16, 32 and 8
   devices for the three ratios rather than 8, 16 and 8. Either a size whose eligibility differs
   across the reported seeds is reported "not measurable" in the seed where it is ineligible, or
   the entry point is taken as the smallest size eligible at EVERY reported seed. The plan states
   both and selects neither.
2. **No session CHAINING happens in a 3-minute run. ADOPTED BY D95 (1)** as the second reason the
   pilot moves to 600 s. The shortest EVAL session is exactly 300 s,
   so at 180 s every robot device is still inside its first session and `sessions completed` is 0
   in every pilot cell. D83's chaining only takes effect at the 600-s run length, where it is
   substantial: 22 completed sessions at 50:50 / 64 devices and 33 at 25:75 / 64.
3. **Clip repeats start at 32 to 64 dashcam devices on a 600-s run** (209 repeated plays at
   50:50 / 64, 459 at 75:25 / 64), because 300 clips at a 37.87-s mean duration cover only about
   16 plays per device in 600 s. Session repeats are **0 everywhere in the ladder**: the 164-session
   pool is never exhausted at these sizes. Every repeat is a separate play with its own play id
   and, per D84, **repeats are not independent samples**; the count is in every trace's metadata.

---

## 8. Part 4: the real-time fleet emulator

One process holds the whole emulated fleet. Every device action is an entry in a time-ordered
heap released against the wall clock; the gap between when an action was due and when it fired is
logged as its LATENESS for every action.

- **Links (D75).** `upload = bytes * 8 / rate + RTT / 2`, and the serialisation part OCCUPIES the
  uplink while the flight does not. `pull = RTT / 2`. `deliver = RTT / 2 + payload / downlink`.
  Uniform in round 1, per-device in the code.
- **One uplink per device, shared serially.** Monitoring frames, history batches and question
  texts contend FIFO for the same uplink. Test c8 shows a frame offered behind a 30-s history
  batch queueing 216.8 ms behind it, which is the point: uploading history delays the frames
  behind it, and the delay is recorded per transfer and summarised per device rather than folded
  into the transfer time.
- **Modes.** A pushes every instant. B sends `monitor_offer`, waits for `pull_request`, and only
  then starts the upload, so B pays one extra RTT before the bytes move.
- **Fairness is asserted, not assumed.** The emulator computes the CANONICAL fairness digest
  (D96 (2)) over the events it actually PRESENTED, through the same `trace.fairness_digest`
  function, and `run()` RAISES if it differs from the trace's digest for its mode. Coverage is
  `device_register`, `session_start`, `session_end`, `history_append`, `recall_question`, and
  `monitor_offer` in PULL mode or `monitor_frame` in PUSH mode. **A pulled frame is not
  digested**, because which frames exist depends on the arm's pulls; test b shows pull-all and
  pull-none producing the identical digest while serving 357 and 0 of the same opportunities,
  which is exactly the property that exclusion buys.
- **Validity.** A run is marked INVALID if p99 lateness exceeds 50 ms. This is harness validity,
  not a result threshold: it says the emulator could not keep run-clock time at that fleet size
  on that host.
- **Outputs.** `outcomes.jsonl` (one row per opportunity with `t_delivered`, `within_L`, the
  uplink queueing it suffered, whether it was pulled, and the cloud payload), `requests.jsonl`
  when the coordinator keeps one, and `run_meta.json` with `fairness_digest`, `trace_fairness_digest`, the
  digest definition in words, the lateness distribution, CPU, wall time, max RSS and the
  per-device uplink statistics.

The coordinator is an interface, not a dependency: anything with `on_event(event, t)` and
`tick(t)` returning `pull_request` / `cloud_answer` events works, which is how subagent A's
`run_cell` will attach. `StubCoordinator` is the flash stand-in; it admits a fixed number of
requests per whole second, has a fixed service time, and **holds no model**, so it returns no
score and no letter. Every run against it carries `server_kind: "stub"` and
`is_measurement: false`.

---

## 9. Part 5: the offline scorer, and the analysis plan

The scored object is the **standing answer**: the cloud's answer if delivered within L, else the
device's. `device_answers.jsonl` is produced by the trace generator and is never sent to the
coordinator, so no arm can see it. Every row is keyed on the `opportunity_id` the trace generator
ASSIGNED (D96 (1)); the scorer reads that id and never constructs or parses one, and it refuses
to score a run whose fairness digest differs from the trace's digest for that run's mode.

- **Targets are inputs and every setting is reported.** The scorer takes L and p as GRIDS and
  emits one sweep row per cell, with the per-device dashcam breakdown in each row. It never
  selects a setting. D71's guard is implemented as the absence of a selection step.
- **Capacity** is the largest fleet size at which every eligible dashcam device meets its own
  target AND the robot pool meets its target, reported next to the whole ladder and a
  `monotone` flag, because a non-monotone ladder is itself a finding.
- **Dashcam AP** is computed by building a PLAY-level context and handing it to StudyE9b's own
  `ApEngine` through `metrics.streaming_ap`; it is never re-implemented. The 0.5-s decision
  cadence is held forward one point on the 0.25-s AP grid, and a point before a play's first
  standing answer is StudyE9b's MISSING sentinel. Scores cross tiers only after the per-tier
  calibration maps are applied (D57).
- **Three refusals** rather than a number: AP is not computed if any served instant's payload
  carried no cloud score (that would mix a cloud DECISION with a DEVICE score), or if the
  completed plays hold no positive or no negative clip; and no run with a non-stub server is
  scored at all with an INTERIM map.
- **Robot value** is the standing answer's accuracy, the cloud's own accuracy on the answers it
  served, and the device-only accuracy, with the WARM / COLD split taken from the request log's
  `cache_path` (D81). When the coordinator holds no model the scorer reports
  `cloud_answers_available: 0` and leaves the accuracy null; it does not impute.
- **The device-only arm** is computed from the recordings alone, with no run.
- **Intervals** are paired bootstraps of policy minus baseline over devices, questions, plays or
  seeds, with no margins. Against itself an arm returns diff 0.0 and CI [0.0, 0.0] (test d15).
- **Diagnostics** (D64) are read from the coordinator's own logs where they exist: decision kinds
  and hold / decline counts, piece sizes, decision latency, predicted-versus-actual rows tagged
  by traffic mix, plus the emulator's CPU, lateness and the per-device uplink queueing.

`results/orchestration/live2/ANALYSIS_PLAN.md` is written and labelled **DRAFT FOR USER
APPROVAL**. It carries the metrics, the units and what is paired with what, the target sweep
grid, the capacity rule, the interval method and its n, the D77 fleet-size rule, the D79 block
order and stop points, eight exclusion rules, the D84 repeat rule, the D64 diagnostics and the
caveat set. Two items in it are marked **CHOICE** and need a decision: the target sweep grid, and
whether dashcam AP and robot accuracy may ever be combined into one "total task value" number
(the plan says no, and explains why the D89 class weights are not an exchange rate).

---

## 10. Part 6: the flash tests

Stub coordinator only, CPU only, INTERIM map. **111 of 111 checks pass** in
`tests/test_live2_fleet.py`, plus the scale check.

| check | what it establishes |
|---|---|
| schema s1 to s5 | `fleet/events.py` field lists are **identical** to subagent A's `live2/schema.py` on all nine events, **including the D96 (1) `opportunity_id` on `monitor_offer`, `monitor_frame` and `recall_question`**, which A's change landed during this amendment; `make()` rejects a missing or unknown field; `opportunity_id_of` READS the assigned id and refuses an opportunity event that carries none; the scorer treats both `stub` and `fake` as non-measurement servers |
| **(a)** determinism and ids | same seed gives the same trace sha256, the same device-answers sha256 and **the same assigned `opportunity_id`s**; a different seed differs; **the trace FILE is byte-identical across modes A and B** while the fairness digest is per mode by design; every id is flat, unique within the run and carries no parsable structure; **the pull-mode digest covers `monitor_offer` and NOT `monitor_frame`**, the push-mode digest the reverse, the two differ in nothing else, and the covered set is exactly D96 (2)'s with `pull_request` mapping to nothing; all three D67 ratios split a 16-device fleet; an unlisted ratio is refused |
| **(b)** fairness | four arms (push-all, push-scarce, pull-all, pull-none) all reproduce the trace's fairness digest for their mode exactly while serving 357, 109, 357 and 0 of the same 357 opportunities. The arms differ in what they SERVE and not in what arrives, which is what D69 asks for; **pull-all and pull-none produce the IDENTICAL digest**, which is the D96 (2) frame exclusion doing its job; the 0-served arm is the harness-level negative control |
| **(c)** link math | `upload_s(354902) = 0.230766 s`; the serialisation and flight terms separate correctly; a q90 dashcam frame uploads in 59.6 ms; the assumed downlink moves a 300 B answer by 2.4 ms over 1 to 100 Mbit/s; a frame offered behind a history batch queues 216.8 ms; an idle uplink imposes none; the queue reports its own occupancy and queueing distribution |
| **(d)** scorer | the scorer keys on the assigned `opportunity_id` and every id resolves in both `outcomes.jsonl` and `device_answers.jsonl`; on hand-built outcomes: a fully served device attains 1.0 and a never-served device 0.0, so capacity is not met; the robot pool attainment is pooled (15 / 29) and not per device; a pool under the minimum is ineligible and blocks capacity; a device under the instant minimum is excluded and reported; the worst robot device is identified; the WARM / COLD split counts 8 and 7 of the 15 cloud-standing answers with WARM accuracy 1.0 and COLD 0.0 exactly as built; play-indexed AP is computed over 30 completed plays (17 positive, 13 negative) and every value is a probability; the device-only arm is computed from recordings; serving half the fleet moves the AP away from device-only; a paired bootstrap of an arm against itself gives diff 0.0, CI [0.0, 0.0] |
| **(e)** session chaining | over 6 robot devices at 25:75 for 900 s: no session starts while another is open, every `session_end` matches the open session, 7 sessions completed and chained, every first start inside the 30-s stagger window, **history restarts from zero in every new session play** (first batch 1,381 tokens over 15 frames, which is StudyRH4's 90 per image plus the 31-token header once), batch tokens accumulate monotonically, every session play has its own id |
| **(f)** INTERIM refusal | the committed `orin2_calibration.json` is labelled INTERIM; an INTERIM map may score a stub run; it is REFUSED for every non-stub server kind including an absent one; a map is FINAL only if it declares `label: FINAL` AND `fit_sample: dense`; `score_run` itself refuses an otherwise valid non-stub run |

### 10.1 Check (g), scale: 64 devices, 3 minutes, both modes

`results/orchestration/live2/fleet/scale_64/scale_summary.json`. 32 dashcam plus 32 robot
devices, 50:50, seed 1, stub coordinator at 32 requests per second.

Re-run after the D95 / D96 amendment, so these numbers are from the build that assigns
`opportunity_id`s and takes the canonical per-mode digest.

| mode | opportunities | scheduled actions | lateness p50 | p90 | p99 | max | emulator CPU | CPU fraction | max RSS | wall | digest == trace | valid |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A (push) | 9,697 | 25,188 | 0.132 ms | 0.167 ms | **0.216 ms** | 0.912 ms | 1.27 s | 0.7 % | 77 MiB | 180.33 s | yes | yes |
| B (pull) | 9,697 | 44,484 | 0.078 ms | 0.141 ms | **0.165 ms** | 2.132 ms | 1.55 s | 0.9 % | 94 MiB | 180.37 s | yes | yes |

p99 lateness is **230x to 300x** under the 50 ms validity limit and the emulator uses under 1 %
of one core, so the emulator is not the bottleneck at 64 devices on this host, in either mode.
Mode B schedules 1.77x as many actions for the same opportunity stream, which is the extra offer
and pull leg. This is a property of this box, not a result, and it is not comparable with the
pre-amendment run at a precision that would matter: the two differ in the trace's ids and in
what the digest covers, and the box's own scheduling noise moves these numbers by more than the
difference between them.

The trace for this cell is `trace_sha256 = d1ead2b7784d8559...`, with
`fairness_digest_A = f78d38e466b0ab04...` and `fairness_digest_B = 0c553bd5a0bdfdd2...`, and each
mode's run reproduced its own digest exactly.

---

## 11. Ruling 6: the D87 device answer set, identified

D87 names "the exact 4B-I x RECENT answer set StudyR1 used as its device comparator (845
questions, 32.78 %), restricted to EVAL", and requires the session to identify the file, checksum
it, confirm the match, and STOP if it cannot be identified unambiguously. It is identified
unambiguously.

| item | value |
|---|---|
| file | `/home/pragya/Desktop/FM-switching/results/sember/study_o/study_o_q4_trials_fa2.jsonl` |
| bytes | 1,409,111 |
| sha256 | `a847e071696312bcdeabb2b2c9f030dc9386b042f53f955f5ba637c360e3b573` |
| the cell | `model_arm == "4B-I"` and `state_arm == "RECENT"` |
| headline reproduced | **277 / 845 = 32.78 %** |
| restricted to EVAL | **190 / 602 = 31.56 %**, over all 164 EVAL videos |
| the other 243 rows | all DEV; 602 + 243 = 845 exactly, with no row outside the split |

The cell is unambiguous because the same file holds only two other cells, 8B-I x RICH (306 / 845
= 36.21 %) and 4B-T x RICH (261 / 845 = 30.89 %), neither of which is 4B-I x RECENT; the
companion `study_o_q4_trials_4bi_rich_fa2.jsonl` is RICH, not RECENT; and
`study_o_q4_trials.jsonl` is the superseded 520-question pool. `reports/study_r1_cloud32b_sember.md`
line 86 records the same cell as StudyR1's device comparator: "4B-I x RECENT (local) | HF fa2 /
A6000 | 845 | 32.78%".

`data_sources.device_recall_answers()` re-derives 277 / 845 from the file on every load and
raises `MissingInput` if it does not match, so a wrong file or a wrong cell filter stops a run
rather than being scored.

**This resolves Part-1 open issue 6 by naming a THIRD set.** Part 1 reported two candidates and
declined to choose: StudyE7 Job A `4B-D2` (a D2 input, not a RECENT window, 602 EVAL questions at
30.9 %) and StudyClean cell H1 (a literal RECENT window, 845 requests at 32.54 %). D87 picks
neither: it picks the StudyO-Q4 fa2 cell at 32.78 %, which is the one StudyR1 actually compared
against. The caveat D87 requires is carried in `DEVICE_ANSWER_CAVEAT` and appears in every scorer
output header: produced by the 4B on the A6000 / H100, not the Orin.

Device recall COST is the ORIN2 in-process harness per D87 (0.146 s at 11k tokens, 0.225 s at
28k); the server re-send path is used nowhere. Round 1 needs a cost at other history sizes, so
`device_recall_latency_s` interpolates linearly between the two committed points and CLAMPS
outside them rather than extrapolating. That interpolation is DERIVED, not committed, and is
listed in section 13.

---

## 12. Ruling 12: mechanism verification and the results consistency check

### 12.1 Mechanism verification

**This row tests no causal claim**, so there is no causal chain to state: it is an ENGINEERING
TASK row and its own pre-registration says it "bears on no claim by itself". The mechanism
verification that governs round 1 attaches to the H100 runs. What CAN be done on flash, and was,
is the Step-2 and Step-4 discipline applied to the harness quantities themselves, so that a
quantity which is silently zero cannot survive into a measured run:

| quantity the round-1 claims depend on | implemented by | value / range on flash | varies as expected | evidence |
|---|---|---|---|---|
| opportunity stream (the paired unit), each opportunity carrying its assigned id | `trace.generate_trace` | 327 to 51,986 opportunities across the 30 ladder cells | yes, with fleet size, ratio and run length | section 7.2 |
| on-time service, the thing a target is about | `outcomes.within_L` | 0 to 357 of 357 across four stub arms | yes, and it is the only thing that differs between them | test b |
| uplink queueing from history uploads | `links.UplinkQueue` | 0 ms idle, 216.8 ms behind a 30-s batch | yes | test c8, c9 |
| device answer and its own latency | `data_sources.orin_dense_scores`, `device_recall_answers` | 42,014 per-instant scores; 602 EVAL recall answers | per instant, not a constant | section 2 items b, c; section 11 |
| per-tier calibration making tiers comparable | `data_sources.calibrate` | device a = 0.114932, b = 1.174287; cloud a = 0.129472, b = 1.848187 | the two maps are different, so the tier matters | test d13 |
| WARM / COLD cache path | request log `cache_path` | 8 WARM, 7 COLD on the toy; 633 / 633 on the stub run | yes | test d8, d9 |
| task value responding to service | `scorer.dashcam_value` vs `device_only_value` | AP at h = 1.0 s: 0.0164 served versus 0.0218 device-only on the toy | yes, serving moves it | test d13 |
| **negative control** | pull-none arm, and `device_only_value` | 0 of 357 served, and the AP of a run with no cloud answer at all equals the device-only AP by construction | the harness collapses to the device-only null when service is disabled | test b, d12 |

No quantity in that table is zero, constant or absent. The one place where a quantity IS
structurally zero on flash is cloud ANSWER CONTENT: the stub holds no model, so `cloud_score` and
`cloud_letter` are null, and the scorer REFUSES to produce AP or accuracy rather than reporting a
number built on a device score. That refusal is itself tested (section 9).

### 12.2 Results consistency check, six checks

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| Nexar clips in the SH set | 300 | 300 | StudyD14b, carried through CTRL1c and E9b | 1.000 | agree |
| decision instants over the 300 clips at the 0.5-s cadence | 21,098 | 21,098 | this report, Part 1 section 1 (DERIVED) | 1.000 | agree |
| Orin dense per-instant rows | 42,014 | 42,014 | StudyORIN1-dense | 1.000 | agree |
| device comparator, all splits | 277 / 845 = 32.78 % | 32.78 % | `reports/study_o_q4_results_845_fa2.md` line 99; `study_o_q4_separating_cell.md` line 74 gives 277 / 845 | 1.000 | agree |
| S-EMBER EVAL split | 164 videos, 602 questions | 164 videos, 602 questions | StudyB-baselines amendment 2 | 1.000 | agree |
| D2 batch tokens, 15 frames | 1,381 first / 1,350 later | 90 per image plus a 31-token header | StudyRH4 | 1.000 | agree |
| serialisation of 354,902 B at 13.6 Mbit/s | 0.208766 s | 0.209 s | StudyE9 | 0.999 | agree |
| dashcam push-all uplink utilisation | 7.5 % of 13.6 Mbit/s | "about 8 %" | D70 consequence 3 | 0.94 | agree |
| Nexar q90 median frame bytes | 63,897.5 B | 63,897.5 B | `results/cost/study_e10/e10a_sizes.json` | 1.000 | agree |
| EVAL sessions under 10 minutes | 130 of 164 (79 %) | "79 % of EVAL sessions are under 10 min (median 430 s)" | D83 | 1.000 | agree |
| maximum questions in an EVAL session | 6, median 4 | "at most 6 questions (median 4; max 6 in any 600 s window)" | D82 | 1.000 | agree |

No disagreement anywhere near 2x.

**2. Physical plausibility.** Every rate implied by the build is below a committed one, because
nothing here computes. A q90 frame of 63,898 B takes 37.6 ms of serialisation, which is
13.6 Mbit/s by construction and cannot exceed it. The stub's 0.25-s service time is not a model
latency and is labelled as a harness parameter. The emulator's own throughput is the only
measured rate: 25,188 scheduled actions in 180.33 s on 2.17 s of CPU, which is 140 actions per
second at 1.2 % of a core, 11,600 actions per CPU-second. That is plainly feasible for heap pops
and dict writes and implies nothing about the system.

**3. Distribution sanity.** Where a median appears, the spread is reported and is non-degenerate:
per-device dashcam instant counts run 273 to 322 at 180 s and 1,053 to 1,106 at 600 s, not a
constant; per-device robot question counts run 0 to 2 at 180 s; lateness has p50 0.164 ms, p99
0.274 ms, max 4.638 ms, so it is a distribution and not a short circuit; uplink queueing is
exactly 0.0 in the stub runs, which is CORRECT and explained rather than suspicious, because at
7.5 % utilisation a frame almost never finds the uplink busy, and test c8 shows the queue is live
when it is loaded.

**4. Definition audit.**

| object | the definition used here | matches prior |
|---|---|---|
| a dashcam "decision instant" | t = 3.0, 3.5, ... up to the clip duration, the 0.5-s StudyCTRL1c cadence | yes, CTRL1c's own definition audit |
| the AP grid | 0.25 s from t = 3.0 s, StudyE9b `STEP_DENSE` and `T0` | yes |
| a "session" | one PLAY of one S-EMBER EVAL `video_id`, duration read from the id's own `_start_<s>_end_<e>` bounds | yes, the committed session convention |
| a "play" | one whole traversal of one clip or session by one device, with its own play id | NEW, introduced by D84 and D85; no prior definition exists to conflict with |
| win-10, sum-80, sum-200 | not used anywhere in this build | n/a |
| the RTT convention | **a correction to Part 1.** Part 1's section 3 said `upload_s` "reproduces the committed decomposition exactly". It reproduces the SERIALISATION term exactly (0.2088 s) but charges RTT/2 on the upload and RTT/2 again on delivery, where the committed cloud-latency convention charges the full 0.044 s once and omits the answer payload. End to end the two agree on the RTT and this build additionally charges the answer payload, which the committed convention leaves out. Stated here rather than left as an overclaim. |

**5. Claim linkage.** Nothing here bears on a claim. The row bears on approval tests T2, T3 and
T4 by building the measurement side they will be evaluated with, and the pre-registration says
so. No measured quantity is produced, so no quantity needs mapping to `research/CLAIMS.md`.
Nothing in the build measures an object `research/FORMULATION.md` scopes out: no KV moves between
tiers anywhere in this code.

**6. Proxy validity.** Four proxies, all declared, none used for a conclusion because there is no
conclusion:

| proxy | what it actually measures | valid for | status |
|---|---|---|---|
| the 4B on the A6000 / H100 as the robot device answer (D87) | an H100-class 4B's answers, not an Orin's | ordering and first-order value | declared in `DEVICE_ANSWER_CAVEAT`, in every output header. StudyD15 Part A REJECTED it as an exact numerical stand-in |
| the E10a median frame size as every frame's size | the median of 500 Nexar frames | uplink timing only, until Part 2 produces the real manifest | declared as `frame_bytes_source` in every trace's metadata; `--frame-manifest` replaces it |
| linear interpolation between 0.146 s at 11k and 0.225 s at 28k for device recall cost | two committed D2-history points | a cost at intermediate history sizes | DERIVED, flagged in section 13 |
| 13.6 Mbit/s symmetric downlink | nothing; no committed downlink exists | a term that moves a delivery by 2.4 ms over the whole plausible range | ruling 9 accepted it with the sensitivity note; reported in section 3 |

Both protocols are recorded here as the flash-scope instance that ruling 12 asks for. **The live
mechanism verification and the live consistency check come with the H100 runs and are not
discharged by this row.**

---

## 13. Open issues

1. **CLOSED by D96.** The conflict reported here was accepted and ruled on. D96 (1) makes the
   trace generator ASSIGN every `opportunity_id`, unique within the run, present on
   `monitor_offer`, `monitor_frame` and `recall_question` and echoed unchanged by the coordinator,
   which removes the ambiguity rather than resolving it case by case; the ids are now flat
   `opp<n>` labels handed out in the trace's canonical order, so nothing downstream can parse
   them and a repeated clip or session (D84) can never collide. D96 (2) adopted **this session's
   digest definition as canonical** and restricted its coverage to `device_register`,
   `session_start`, `session_end`, `history_append`, `recall_question`, and `monitor_offer` in
   pull mode or `monitor_frame` in push mode; a LIVE1-port digest may appear only as
   `live1_trace_digest`. Both are implemented, and the ambiguity check is kept as a safety net
   rather than as the mechanism, per the ruling.

   **One residual, on subagent A's side and not touched here.** A's `schema.py` has landed the
   `opportunity_id` field on all three events and my field lists now match it exactly, but
   `live2/CONTRACT.md` line 20 still reads "`opportunity_id` on a `cloud_answer` is the
   `instant_id` or `question_id` it answers", which is the prose D96 (1) supersedes. A was told
   to remove it and is mid-build; I did not edit A's files. Until it is removed, the contract
   document and the schema disagree with each other, and `schema.py` is the record by the
   contract's own first paragraph.
2. **CLOSED by D95.** The pilot moves to 600 s at seed 0 and the measurability rule is adopted:
   a fleet size enters the main sweep only if its robot pool reaches 20 questions at the main run
   length, smaller sizes are reported "robot part not measurable" and never as passes, and size 4
   is kept as a harness sanity check. One point the rule does not yet settle is recorded in
   section 7.3 item 1 and in `ANALYSIS_PLAN.md` section 3 as a CHOICE: **the entry point is
   seed-dependent at the boundary**, so 8 devices at 50:50 is eligible at seed 1 and not at
   seed 0, and 16 devices at 75:25 likewise. The plan states both readings and selects neither.
3. **The run-time reading of "staggered seeded offset"** (section 7.1). The alternative reading
   puts the device part-way into its first clip or session, which contradicts D83's "history
   starts from zero" and D85's "plays cut by the run end". I chose the run-time reading, said so,
   and left `stagger_s` a parameter at 30 s. If the user meant the other reading, the first
   session's pre-existing history has to be specified, because nothing committed says how much
   history a device joining mid-session has already uploaded.
4. **Device recall latency at history sizes other than 11k and 28k is interpolated.** D87 gives
   two committed points from the ORIN2 in-process harness, both on D2 image histories on one DEV
   video; round 1 needs a cost at every size, so the code interpolates linearly between them and
   clamps outside. The interpolation is DERIVED. Separately, ruling 8 is recorded as instructed:
   the RECENT-versus-D2 question is **moot for scoring**, because a target is on-time CLOUD
   service and the device answer is the fallback, so the device's own latency never decides
   whether a target is met. It still enters the diagnostics, which is why the interpolation is
   flagged rather than dropped.
5. **The 32B cloud calibration map for JPEG input does not exist yet**, and the dense refit of
   BOTH tiers is an H100 task (D86). Until then the committed `orin2_calibration.json` maps are
   INTERIM, the scorer refuses any non-stub run with them, and the event-anchored versus dense
   issue stands as recorded: the D3-fitted device slope is 3.007x steeper than a dense D14b-DEV
   fit (+0.114603 versus +0.038113), and round 1 applies the map to dense whole-clip instants.
   The committed file was NOT edited to add a label; the label is derived conservatively in code,
   so an absent declaration can never be read as FINAL.
6. **Part 2 has not run, and the Pillow version E10a used is still unrecorded anywhere.** The
   scripts record the versions THEY use, and the check is distributional against E10a's committed
   quartiles, but if those quartiles are flagged there will be no way to tell a version
   difference from a recipe difference. The only mitigation available is to run the encode in the
   E10a venv (`/home/pragya/.venvs/fm-switching-vllm` on the h100nvl host) and record what it
   reports.
7. **A median frame size stands in for a distribution until Part 2 runs.** Every trace generated
   before the manifest exists charges every Nexar frame 63,898 B and every S-EMBER D2 frame
   24,570 B. The E10a interquartile range for Nexar q90 is 49,810 to 75,682 B, so an individual
   frame's upload time can be 29 ms rather than 37.6 ms, or 44.5 ms. Against a 1.0-s dashcam
   deadline this is small, but it is a real narrowing of the uplink's variance and the trace
   metadata says which source was used.
8. **Two CHOICE items in the analysis plan need a decision**: the target sweep grid, and whether
   dashcam AP and robot accuracy may be combined into a single "total task value" number. The
   plan says no to combining and explains why the D89 class weights are an online objective's
   weights rather than a reported exchange rate.
9. **Multiplicity is not corrected and no correction is claimed.** 7 baselines x 2 memory
   settings x 5 fleet sizes is a large family; the plan says the intervals are descriptive and
   offers Benjamini-Hochberg over the primary family as a CHOICE.
10. **The 164-session pool, not the clip pool, is the first thing a large fleet exhausts at
    25:75.** Session repeats are 0 everywhere in the measured ladder, but at 25:75 with 64
    devices the 48 robot devices already consume 81 of the 164 sessions in 600 s; at 128 devices
    the pool is exhausted and repeats begin, with the D84 consequence that they are not
    independent samples. Worth knowing before fleet sizes are pushed past 64.
11. **Nothing in this report is a finding, and no sweep was run.** The live mechanism
    verification and the live consistency check belong to the H100 runs (ruling 12). Section 12
    is the flash-scope instance of both protocols and does not discharge them.

---

## 14. Files created or changed

Created in this resumed session:

- `experiments/orchestration/live2/fleet/trace.py`
- `experiments/orchestration/live2/fleet/emulator.py`
- `experiments/orchestration/live2/fleet/tests/test_live2_fleet.py`
- `experiments/orchestration/live2/fleet/tests/test_scale.py`
- `experiments/orchestration/live2/scorer/score.py`
- `experiments/orchestration/live2/data/encode_jpeg.py`
- `experiments/orchestration/live2/data/build_manifest.py`
- `results/orchestration/live2/ANALYSIS_PLAN.md`
- `results/orchestration/live2/fleet/trace_ladder_seed1.json`
- `results/orchestration/live2/fleet/scale_64/` (`scale_summary.json`, the trace metadata with
  its sha256 and opportunity digest, and each mode's `run_meta.json`, plus `REGENERATE.md`). The
  17 MB of stub `trace.jsonl`, `device_answers.jsonl`, `outcomes.jsonl` and `requests.jsonl` were
  deleted after the summary was taken: they are byte-for-byte regenerable from the seed with one
  command, which `REGENERATE.md` gives, and a regenerated trace is verifiable against the
  committed `trace_sha256`, `fairness_digest_A` and `fairness_digest_B`.

Changed in this resumed session:

- `experiments/orchestration/live2/fleet/events.py` (added `session_start` / `session_end` per
  D83 and A's schema; added `opportunity_id` to the three opportunity events per D96 (1), with
  `opportunity_id_of()` now reading it; added the `PENDING_D96` tolerance;
  `check_against_schema()` passes)
- `experiments/orchestration/live2/fleet/data_sources.py` (added the ruling inputs: EVAL
  sessions, the D87 device answers with a self-check, device recall latency, the dense Orin
  scores keyed on `file_name`, the calibration label rule, the caveat texts)
- `reports/study_live2_fleet.md` (this file; sections 1, 2 and 3 are Part 1 verbatim)

Changed in the bounded D95 / D96 amendment:

- `experiments/orchestration/live2/fleet/events.py` (D96 (1) field, the reading helper, the
  `PENDING_D96` tolerance)
- `experiments/orchestration/live2/fleet/trace.py` (assigned `opportunity_id`s;
  `fairness_digest` and `_digest_tuple` replacing `opportunity_digest`; both modes' digests in
  the trace metadata)
- `experiments/orchestration/live2/fleet/emulator.py` (the three wire events carry
  `opportunity_id`; the presented stream now covers the full D96 (2) event set; `_sent_digest`
  calls `trace.fairness_digest`; the resolver demoted to a documented guard)
- `experiments/orchestration/live2/scorer/score.py` (keyed on the assigned id; the digest check
  is per mode and reads `fairness_digest`)
- `experiments/orchestration/live2/fleet/tests/test_live2_fleet.py` (121 checks, 10 of them new
  for D96)
- `results/orchestration/live2/ANALYSIS_PLAN.md` (D95's pilot length, seed and measurability
  rule with the seed-dependence table; D96's ids and digest in the pairing and exclusion rules)
- `results/orchestration/live2/fleet/scale_64/` (re-run under the new ids and digest)

Created in the earlier session and unchanged: `experiments/orchestration/live2/fleet/links.py`.

**Not touched.** `experiments/orchestration/live2/schema.py` and
`experiments/orchestration/live2/CONTRACT.md` (subagent A owns both; they were read only).
`research/policy_design_log.md`, `research/policy_spec_v4.md`, `research/policy_ablations.md`,
`research/EXPERIMENTS.md`, `research/STATUS.md`, `results/INDEX.md`. Any earlier result file. The
10,660 StudyD15 frames, which are not reachable from this box at all. Only read-only git commands
were run; no `git add`, `commit`, `push`, `rebase`, `stash` or `reset`.

---

## 15. Amendment 2: the D97 robot-measurability entry point

**Authority: D97 (user ruling 2026-11-17, row pending).** The ruling is not yet a committed row
in `research/policy_design_log.md`, because the user supplies exact row text; the ruling text
itself is the authority, and the absence of the row is not a prompt-versus-log disagreement.
D56 and D62 to D96 remain as before. Bounded to four items; nothing else in this report changed.

**The rule.** Robot-pool eligibility (at least 20 pooled questions per run, D82) is a property of
the TRACE, so it is fixed from traces before any GPU run. A fleet size enters a main-sweep
comparison only if its robot pool is eligible at EVERY seed that will be reported for that
comparison: seeds 1, 2 and 3. The pilot (seed 0) only reports which of its sizes were measurable
at seed 0; seed 0 never sets an entry point. A size is never made measurable by averaging or
borrowing across seeds. This supersedes the two-option CHOICE left open by amendment 1, which is
not re-opened.

### 15.1 The eligibility table

`results/orchestration/live2/fleet/eligibility/robot_eligibility_4_to_128.csv` (1,500 rows) and
`robot_eligibility_summary.json`. Every integer fleet size from 4 to 128, all three ratios, 600-s
runs, seeds 1, 2 and 3 plus seed 0 for reference. Trace-only: no server, no GPU, no model. Each
row carries the pooled robot question count and its verdict, the minimum per-device dashcam
instant count and how many dashcam devices clear 200, distinct and repeated clip plays and
sessions with both pool sizes, sessions completed, history batches, the dashcam / robot split,
and the total opportunity count.

Counting uses `trace.generate_trace(..., count_only=True)`, which runs the generator's OWN
control flow and skips only the construction of wire records and device-answer rows. It is a skip,
not a second implementation, and test (h) asserts the two modes produce identical stats on four
cells spanning both run lengths, all three ratios, an odd size and the pilot seed.

**The split rule for odd sizes**, stated because it is not obvious:
`n_dashcam = int(round(n_devices * d / (d + r)))` with Python's **round-half-to-even**, and
`n_robot = n_devices - n_dashcam`. At 50:50 an odd size therefore does not alternate regularly:
5 gives 2 dashcam and 3 robot, 7 gives 4 and 3, 9 gives 4 and 5, 11 gives 6 and 5. This is the
existing implemented behaviour, was not changed, and the table states the actual split for every
size so nothing hides behind the rule.

### 15.2 Per-ratio summary

| ratio | D97 entry point (seeds 1, 2, 3) | sizes above it NOT eligible at all three | monotone | pooled questions at the entry point (s1 / s2 / s3) | last ineligible size below it | seed-0 entry (reference only) | sizes eligible at all three seeds |
|---|---|---|---|---|---|---|---|
| 25:75 | **5** | none | yes | 22 / 22 / 23 | 4 (14 / 15 / 19) | 7 | 124 of 125 |
| 50:50 | **8** | none | yes | 22 / 21 / 22 | 7 (14 / 15 / 18) | 12 | 121 of 125 |
| 75:25 | **14** | none | yes | 22 / 20 / 22 | 13 (14 / 15 / 18) | 20 | 115 of 125 |

Four things the sweep settles, none of which was visible in the coarse powers-of-two ladder of
section 7.2:

1. **Eligibility is MONOTONE in fleet size at every ratio over seeds 1 to 3.** The non-monotone
   column is empty: no size above an entry point fails at all three seeds. This is an EMPIRICAL
   result for this seed set and is not relied on. The scorer still evaluates every size actually
   chosen and reports any non-monotone size it finds, exactly as D97 requires.
2. **The entry point is where the fleet first holds FOUR robot devices**, at every ratio. Four
   robot devices give 20 to 23 pooled questions and three give 14 to 19, so the binding quantity
   is the ROBOT DEVICE COUNT and not the fleet size; the ratio only sets how large a fleet that
   takes. This is why the three entry points are 5, 8 and 14 rather than anything about dashcam
   load.
3. **Seed 0 is systematically the strictest seed** (entry 7 / 12 / 20 against 5 / 8 / 14), which
   is exactly why D97 forbids it from setting an entry point. Had the pilot seed been allowed to
   set one, it would have excluded sizes that every reported seed finds measurable. Amendment 1
   reported the boundary as "seed-dependent" from four coarse cells; the full sweep shows the
   dependence is a systematic offset of the pilot seed, not noise scattered across sizes.
4. **The dashcam minimum never binds anywhere.** The smallest per-device instant count over all
   1,500 cells is 996 against D71's minimum of 200, and **0 of 1,500 cells** has a dashcam device
   below it. D71's dashcam minimum is therefore not a constraint on the fleet ladder at 600 s at
   any size up to 128, at any ratio, at any of the four seeds.

Pool exhaustion, for the D84 repeat rule: the first size at which a clip play repeats is **23**
devices at 75:25, **34** at 50:50 and **67** at 25:75; **sessions repeat only at 25:75, from 111
devices**. At the top of the ladder the repeat counts are large and must be read with any result
there: at 128 devices and 75:25 the fleet makes 1,232 repeated clip plays over all 300 clips and
holds only 54 distinct sessions.

### 15.3 What the scorer now does

`scorer/score.py` gained three functions and one refusal:

- `eligibility_table(paths)` builds `{ratio: {size: {seed: eligible}}}` from TRACE metadata or
  from the eligibility CSV. It never needs a run, a server or a GPU, which is what makes D97's
  "fixed from traces before any GPU run" an implementable rule rather than an intention. Two
  conflicting verdicts for one cell raise rather than resolve.
- `d97_sweep_sizes(table, ratio, seeds)` labels each size `included` or
  **`robot part not measurable`**, with the per-seed verdicts and the reason, and returns the
  entry point, the included sizes, and any non-monotone size above the entry point. A size with
  no trace for a reported seed is NOT measurable rather than assumed either way.
- `d97_pilot_labels(table, ratio)` labels pilot sizes "measurable at seed 0" or "not measurable
  at seed 0" and **returns `entry_point: None`**. There is deliberately no entry point to read
  out of a pilot.
- Passing the pilot seed inside a reported seed set is REFUSED, so seed 0 cannot reach an entry
  point by being included in the set.

`seeds` is a parameter, not a constant, because D79 made a third seed conditional while D97 fixes
the reported set at {1, 2, 3}. The rule is applied to the set that will actually be reported;
what is forbidden is claiming a {1, 2, 3} entry point while reporting two seeds. The plan states
this and test g2e covers it.

### 15.4 Tests

**135 of 135 checks pass** (121 before this amendment), with 14 new:

| check | what it establishes |
|---|---|
| g2a to g2d | a size eligible at seeds 1 and 2 but NOT 3 is EXCLUDED and labelled "robot part not measurable" with the failing seed named; the entry point is the smallest size eligible at every reported seed; a larger ineligible size is reported as non-monotone rather than assumed eligible; no size is included by averaging over a subset of seeds |
| g2e | with only seeds 1 and 2 reported, the rule applies to THAT set |
| g2f | a size with no trace for a reported seed is NOT measurable, not assumed |
| g2g | **a pilot run never yields an entry point**: `entry_point` is present and `None`, and the per-size labels are the seed-0 wording |
| g2h | the pilot seed may not appear in a reported seed set |
| g2i | the eligibility table is read from trace metadata with no run at all |
| h (4 cells) | `count_only` stats are IDENTICAL to the full build, across both run lengths, all three ratios, an odd size and the pilot seed |
| h2 | the odd-size split follows round-half-to-even, stated with the actual splits rather than assumed |

### 15.5 Files created or changed in amendment 2

Created:

- `experiments/orchestration/live2/fleet/eligibility.py`
- `results/orchestration/live2/fleet/eligibility/robot_eligibility_4_to_128.csv` (1,500 rows)
- `results/orchestration/live2/fleet/eligibility/robot_eligibility_summary.json`

Changed:

- `experiments/orchestration/live2/fleet/trace.py` (the `count_only` skip)
- `experiments/orchestration/live2/scorer/score.py` (`eligibility_table`, `d97_sweep_sizes`,
  `d97_pilot_labels`, the pilot-seed refusal, and the D97 paragraph in the module docstring)
- `experiments/orchestration/live2/fleet/tests/test_live2_fleet.py` (135 checks, 14 new)
- `results/orchestration/live2/ANALYSIS_PLAN.md` (the one-page decision index with 40 rows and 8
  CHOICE items; the D97 rule replacing the two-option text; the reported seed set fixed at
  {1, 2, 3}; the section 15.2 summary; the D97-versus-D79 note on the third seed; exclusion
  rule 3 rewritten)
- `reports/study_live2_fleet.md` (this section)

Nothing else was touched. `live2/schema.py` and `live2/CONTRACT.md` remain subagent A's and were
not written; the parent confirms A's change has fully landed and the superseded CONTRACT.md prose
is gone, so the residual recorded in amendment 1's open issue 1 is closed and needed no action
here. The design log, `research/EXPERIMENTS.md`, `research/STATUS.md` and `results/INDEX.md` were
not edited. Read-only git only.

### 15.6 What amendment 2 does NOT do

Open issues 3 to 11 of section 13 stand exactly as delivered and were not actioned. The
seed-dependence CHOICE of amendment 1 is closed by D97 and was not re-opened. No measurement was
made: the eligibility table is arithmetic over committed traces, and nothing in it is a finding
about the system.

---

## 16. StudyLIVE2-fix: D101 (the part-way join), D103 (the analysis-plan rulings), D105 and D99

**Authority: D98 to D105, committed in `research/policy_design_log.md` at 80fe119 and the
amendment the parent made tonight.** Four items, bounded: (1) implement D101 in the fleet;
(2) recompute the D97 eligibility table under D101, trace-only; (3) apply the D103 rulings to
`ANALYSIS_PLAN.md` and add D99 and D105 to it; (4) implement the scorer side of D103 (e), (f) and
(h), D105's out-of-fold maps and the D101 preload, then re-run every test and the 64-device scale
check. Flash only, CPU only, stub coordinator only. **Nothing in this section is a measurement**:
every number is arithmetic over committed traces, or this host's own harness timing.

The design log, `research/policy_spec_v4.md`, `research/policy_ablations.md`,
`research/EXPERIMENTS.md`, `research/STATUS.md` and `results/INDEX.md` were **not** edited;
`live2/schema.py` and `live2/CONTRACT.md` are subagent A's and were not written. Read-only git
only.

### 16.1 D101: robots join their first session part-way

| item | what the fleet now does |
|---|---|
| the join draw | `join_frac` ~ U[0, 0.5), seeded on its own RNG stream (`"<seed>|join"`), drawn per robot in a fixed device order; the OFFSET is that fraction of the device's own first session duration. The draw is recorded per device in `trace_meta.json` under `robot_join` (`join_frac`, `join_offset_s`, `first_session`, `first_session_duration_s`) |
| questions | a question whose session time is before the join point is **not emitted and not counted**; the count of what was dropped is in the trace stats as `robot_questions_before_join` |
| the preload | one `history_preload` per joined session at `t = 0`, holding exactly the D2 frames in (0, join] with StudyRH4's accounting (90 tok/img plus the 31-tok header once, which the preload carries because it is the session's first holding). **No uplink time is charged**: the emulator hands it to the coordinator at t = 0 without touching the device's uplink queue, so it never delays a frame behind it |
| batches after t = 0 | the same 30-s session-local grid as before. A batch carries only the frames the preload did not, so no frame is held twice and none is dropped, and a batch after a preload does not carry a second header. A window entirely before the join point produces no batch |
| later sessions | start from zero, exactly as D83 says; they have no preload and `joined_part_way` is false |
| dashcam | unchanged: the run-time stagger in [0, 30 s) and the complete-play rule (D85) |
| the digest | D96 (2)'s coverage **plus `history_preload`**, with the row `(device_id, "history_preload", "%.6f" % t, session_id, str(int(est_tokens)), "")` |

**One reading D101 does not spell out, recorded here.** D101 says the preload is at `t = 0`, so a
robot device **registers at t = 0 and no longer takes a run-time stagger offset**: a device that
has not yet registered cannot declare a preload. The join draw decorrelates batch boundaries and
question phases across robots in the stagger's place, and the dashcam stagger of a given seed is
unchanged, because the robot draw is still taken from the stagger stream and only ignored. If the
user meant a robot to carry **both** a run-time offset and a join point, that is a one-line change
to `trace.py` and the eligibility table has to be recomputed again.

**Schema agreement with subagent A: byte for byte.** After the parent's word,
`events.check_against_schema()` returns `note = "field lists identical"`, `d96_pending = false`,
over all ten events including `history_preload = (device_id, session_id, frame_refs, est_tokens,
t)`. The digest row was also compared against A's own `traces.py::_fairness_row` on the same
event and the two tuples are identical. **No schema mismatch, so no stop condition.**

### 16.2 The D97 eligibility table, recomputed under D101

`results/orchestration/live2/fleet/eligibility_join/robot_eligibility_4_to_128.csv` (1,500 rows)
and `robot_eligibility_summary.json`. Sizes 4 to 128, all three ratios, 600-s runs, seeds 1, 2
and 3 plus seed 0 for reference. The pre-D101 table is left in place at `.../fleet/eligibility/`
so the two can be compared. **These entry points are recomputed under D101; design-log row pending (planner will log as D107).** Each row also carries `questions_before_join`,
`preloads_emitted`, `preload_tokens_min / median / max / total` and
`join_offset_min / median / max_s`.

| ratio | entry point (seeds 1, 2, 3) | pooled questions there (s1 / s2 / s3) | last ineligible size below | per-seed entry (s1 / s2 / s3) | seed-0 entry (reference) | non-monotone sizes above entry | sizes eligible at all three seeds |
|---|---|---|---|---|---|---|---|
| 25:75 | **5** | 23 / 23 / 23 | 4 (14 / 15 / 20) | 5 / 5 / 4 | 5 | none | 124 of 125 |
| 50:50 | **8** | 23 / 23 / 23 | 7 (14 / 15 / 20) | 8 / 8 / 5 | 8 | none | 121 of 125 |
| 75:25 | **14** | 23 / 23 / 23 | 13 (14 / 15 / 20) | 14 / 14 / 11 | 14 | none | 115 of 125 |

**The entry points did not move: 5 / 8 / 14, the same as before D101.** The join removes the
questions ahead of it and brings every later session in the chain forward by the same offset, and
over a 600-s run those two effects very nearly cancel. What did change:

1. **Which seed binds.** Seed 3 now enters earlier at every ratio (4 / 5 / 11 against 5 / 8 / 14),
   so the all-seeds entry point is set by seeds 1 and 2.
2. **Seed 0 is no longer the strictest seed.** Its entry points were 7 / 12 / 20 before D101 and
   are 5 / 8 / 14 now, the same sizes as the reported seeds. The rule is untouched - the pilot
   seed still never sets an entry point (D95 (7), D97) - but amendment 2's observation that the
   pilot seed "would have excluded sizes every reported seed finds measurable" **no longer holds
   and must not be repeated**.
3. **Session repeats start earlier.** A joined first session ends sooner, so the chain consumes
   more of the 164-session pool: sessions now repeat from **73 devices at 25:75 and 109 at 50:50**
   (before: only at 25:75, from 111), and never at 75:25 inside the table. Clip-play repeats are
   unchanged, from 23 / 34 / 67 devices at 75:25 / 50:50 / 25:75.

**The pooled counts over the pilot ladder** (bold = first cell at or above D82's 20; "enters
from" is over every integer size, not only the ladder):

| ratio | seed | 4 | 8 | 16 | 32 | 64 | enters from |
|---|---|---|---|---|---|---|---|
| 50:50 | 1 | 7 | **23** | 44 | 80 | 153 | 8 |
| 50:50 | 2 | 11 | **23** | 43 | 75 | 154 | 8 |
| 50:50 | 3 | 11 | **23** | 34 | 73 | 148 | 5 |
| 50:50 | 0 | 9 | **20** | 35 | 72 | 165 | 8 |
| 75:25 | 1 | 5 | 7 | **23** | 44 | 80 | 14 |
| 75:25 | 2 | 4 | 11 | **23** | 43 | 75 | 14 |
| 75:25 | 3 | 5 | 11 | **23** | 34 | 73 | 11 |
| 75:25 | 0 | 2 | 9 | **20** | 35 | 72 | 14 |
| 25:75 | 1 | 14 | **30** | 62 | 122 | 235 | 5 |
| 25:75 | 2 | 15 | **30** | 58 | 111 | 218 | 5 |
| 25:75 | 3 | **20** | 28 | 55 | 108 | 226 | 4 |
| 25:75 | 0 | 13 | **27** | 57 | 121 | 248 | 5 |

**The preload sizes, which are the point of D101.** At each ratio's entry point the four robot
devices arrive holding 0 to 11,101 D2 tokens each (median 3,271 / 6,061 / 4,081 at seeds 2 / 1 /
3; 15,303 to 20,464 tokens in total across the four). At 64 devices and seed 1 the per-device
maximum is 11,101 tokens at 50:50 and 75:25 and 11,641 at 25:75, with join offsets spread from
1.3 s to 258.4 s. Over the whole table the preload runs from **0 to 21,721 tokens** per device,
and in **941 of the 1,500 cells** at least one robot joined inside the first 2-s D2 stride and so
held nothing: that is the bottom of the intended spread, not a fault. The join removed **36,648
questions** in total that the pre-D101 traces would have asked before the join point.

The **dashcam** minimum still never binds: the smallest per-device instant count over all 1,500
cells is **996** against D71's 200, and **0 of 1,500** cells has a dashcam device below it.

### 16.3 The analysis plan

`results/orchestration/live2/ANALYSIS_PLAN.md`, header changed from **DRAFT FOR USER APPROVAL**
to **APPROVED 2026-11-17 (D103), user may revisit**, with a change log at the end.

| item | what the plan now says |
|---|---|
| (a) | the sweep grid is kept and labelled **SENSITIVITY**; the **headline** is the D71 / D82 starting values (L_dash 1.0 s, p_dash 0.25, L_rob 5.0 s, p_rob 0.90) |
| (b), (c), (d) | accepted as written, each now citing D103: sample-and-hold onto the 0.25-s AP grid; linear interpolation of the device recall cost, DERIVED and unexercised; dashcam AP and robot accuracy never summed |
| (e) | AP-difference bootstrap **n = 1,000**, with the measured cost beside it |
| (f) | no multiplicity correction and none claimed, with the **PRIMARY family** fixed in advance: policy vs each of the 7 GPU baselines at the two break sizes, tight memory, 50:50, push-all (block 1). Everything else is **EXPLORATORY** |
| (g) | replaced by **D101**: the robot join, the preload, the dashcam stagger, and the recomputed entry points |
| (h) | the E10a median is for **flash tests only**; a measured run reads per-frame bytes from the Part-2 manifest (D91) and is **refused** otherwise |
| D99 | one fixed 100-ms decision period for every arm, the cap K reported as a setting if used, and the coordinator's own latency counted and never netted out; added to the diagnostics list |
| D105 | both maps 5-fold cross-fitted **by clip**, each clip scored with the map from the folds that **exclude** it, the fold assignment taken from the calibration file, and a FINAL map without one refused; added to the index, section 4.1, the exclusion rules and the output caveats |

**(e), timed as D103 asks.** One AP difference through `ap_diff_bootstrap`, on this host, CPU
only, over the completed plays of a 600-s 50:50 trace:

| completed plays | positive / negative | n = 200 | n = 1,000 |
|---|---|---|---|
| 120 (16 devices) | 61 / 59 | 0.026 s | **0.129 s** |
| 237 (32 devices) | 127 / 110 | 0.048 s | **0.239 s** |

So n = 1,000 costs about **0.13 to 0.24 s of CPU per AP difference**, and the whole primary family
of differences is seconds of work. The old n = 200 was not buying anything.

### 16.4 The scorer

| change | what it does |
|---|---|
| D103 (e) | `N_BOOT_AP = 1000` |
| D103 (f) | `classify_family(policy, baseline, break_sizes)` labels every comparison **PRIMARY** or **EXPLORATORY** and gives the reason; `compare()` carries the label. The break sizes are an INPUT, so the family cannot be chosen after the result. A run header that does not record its memory setting cannot be claimed as tight memory, so the comparison is EXPLORATORY and the output names the missing field |
| D103 (h) | `check_frame_bytes_source` refuses a measured run whose `frame_bytes_source` is not the Part-2 manifest; `is_measured_run` is the single definition of "measured" (a non-stub server AND a FINAL map), and `score_run` calls the check |
| D105 | `DS.calibration` parses `folds` (`n_folds`, `by`, `assignment`, one map per held-out fold); `map_for(cal, key, clip)` returns the out-of-fold map, refuses a clip the file places in no fold and refuses a missing per-fold map; both AP paths (served and device-only) now look the map up per clip; `check_calibration` **refuses a FINAL map with no fold assignment** rather than applying it pooled; `calibration_use` puts the fold state in every output header |
| D101 | `history_preload(lo)` reports the preload count, whether all are at t = 0, the token spread, the join-offset spread and the rule, in every score header; a run whose preload count differs from its trace's is **refused** |
| D99 | the diagnostics carry the decision period, the cap K and whether the run header recorded either |
| D97 | the "row pending" wording is dropped now that D97 is committed |

### 16.5 Tests

`experiments/orchestration/live2/fleet/tests/test_live2_fleet.py`: **234 of 234 checks pass**
(was 147 after the D96 amendment; 87 new or rewritten). Stub coordinator, CPU only, INTERIM map.

| group | what it establishes |
|---|---|
| **d101 a-v** (62 checks, most of them per robot device) | every robot's first session starts at t = 0 and is joined part-way; the join point is in [0, 0.5 x duration); the draw is recorded per device in `trace_meta`; later sessions start from zero; no emitted question lies before the join point and **exactly** the questions at or after it are emitted; the preload holds exactly the pre-join D2 frames with the right accounting, at t = 0, flagged not uplink-charged; no frame is held twice and none is dropped between the preload and the batches; the skipped questions are counted; the preload sizes are reported; **dashcam devices keep the run-time stagger** and robots register at t = 0; the join draw is deterministic in the seed and the k-th robot's fraction does not depend on the ratio; **the fairness digest covers the preload**; every preload reaches the coordinator at t = 0 in A's exact field form; **a preload occupies no uplink slot and queues nothing**; the run still reproduces the trace digest; the scorer reports the preload, never scores it as an opportunity, and refuses a run whose preload count differs from its trace's |
| **d105 a-h** (8) | a pooled FINAL map is refused for a real server AND for a stub; a folded FINAL map passes; the assignment comes from the file; two clips in different folds get **different** maps; a clip in no fold is refused rather than scored pooled; a missing per-fold map is refused; an INTERIM map has no folds and the header says it was applied pooled |
| **d103h 1-5** (5) | the E10a median is allowed for a stub run and **refused** for a measured one; a manifest source is accepted; `is_measured_run` is true only for a non-stub server with a FINAL map; the frame-bytes source is in every score header |
| **d103f 1-10** (12) | the primary family holds only for policy vs one of the seven at a break size, tight, 50:50, push-all; a size outside the break sizes, a missing break-size list, another ratio, pull mode, roomy memory, an unrecorded memory setting, a baseline-versus-baseline pair and an arm outside the seven are each EXPLORATORY; the label travels with every comparison; `N_BOOT_AP == 1000` |
| **a11** (rewritten) | the digest covers exactly the D96 (2) set **plus `history_preload`**, and the preload row is the exact tuple A specified |
| **e4, e5, e6, e6b** (rewritten) | the first session is joined part-way; the session's **first holding** carries the D2 header once, whether that holding is a preload or a first batch; holdings accumulate monotonically; a batch after a preload carries no second header |

**Check (g), the 64-device scale run under D101, both modes.**
`results/orchestration/live2/fleet/scale_64_join/scale_summary.json`. 32 dashcam plus 32 robot
devices, 50:50, seed 1, 180 s, stub coordinator at 32 requests per second, real time. The
trace is `trace_sha256 = c737d67fc65a182e...`, `fairness_digest_A = a0de356f8c9cf64a...`,
`fairness_digest_B = 52436fcfe872d7be...`; 31 of the 32 robots carry a preload (one joined inside
the first 2-s stride), the fleet holds 57 pooled robot questions and the join dropped 25.

| mode | opportunities | scheduled actions | lateness p50 | p90 | p99 | max | emulator CPU | CPU fraction | max RSS | wall | digest == trace | valid |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A (push) | 9,704 | 25,307 | 0.130 ms | 0.143 ms | **0.169 ms** | 2.657 ms | 0.98 s | 0.55 % | 78 MiB | 180.33 s | yes | yes |
| B (pull) | 9,704 | 44,603 | 0.077 ms | 0.139 ms | **0.163 ms** | 3.689 ms | 1.60 s | 0.89 % | 96 MiB | 180.37 s | yes | yes |

p99 lateness is **296x and 307x** under the 50 ms validity limit and the emulator uses under 1 %
of one core, so adding the preload path changed nothing about whether the emulator can keep time
at 64 devices on this host. **Condition to state explicitly:** the 1,500-cell trace sweep of
section 16.2 was running on one other core of this 24-core box during both runs, so these
numbers carry that much contention; at 300x margin it cannot change the verdict, and they are
not comparable with the pre-D101 run at any finer precision (section 10.1 said the same of box
noise).

### 16.6 Mechanism verification (CLAUDE.md), for this amendment

**Not applicable as a causal test, and nothing here may be read as one.** No sweep was run, no
policy was compared to a baseline, and nothing in this section tests a causal claim: the work
builds the instrument. The protocol attaches to the measured H100 runs and is **not discharged**
by anything here. What this amendment does do is restore the mechanism D101 exists to create -
**cold-rebuild pressure, from a prefix the arm did not watch being built** - which before D101 was
**ABSENT** from every round-1 trace, because every history started at zero. Section 16.2 shows the
quantity that implements it is now non-zero and varies: the preload runs from 0 to 21,721 D2
tokens per device with join offsets from 1.3 s to 258.4 s. Whether it binds on any budget is a
question for the measured runs, and it must be instantiated there under Step 2 before any sweep.

### 16.7 Results consistency check (CLAUDE.md), six checks

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree |
|---|---|---|---|---|---|
| D97 entry points (25:75 / 50:50 / 75:25) | 5 / 8 / 14 | 5 / 8 / 14 | `research/EXPERIMENTS.md` D97 row, report section 15.2 | 1.00 | agree |
| pooled robot questions, worst-changed cell of 1,500 | 9 | 6 | `.../fleet/eligibility/robot_eligibility_4_to_128.csv` (75:25, seed 0, 9 devices) | **1.50** | agree, under the 2x bar; D101 removes pre-join questions and brings later sessions forward, so a cell can move either way |
| pooled questions at the entry point | 23 / 23 / 23 | 22 / 21 / 22 and 22 / 22 / 23 | report section 15.2 | 1.00 to 1.10 | agree |
| smallest dashcam instant count over all cells | 996 | 996 | report section 15.1 | 1.00 | agree |
| cells with a dashcam device under 200 instants | 0 of 1,500 | 0 of 1,500 | report section 15.1 | - | agree |
| first size with clip-play repeats | 23 / 34 / 67 | 23 / 34 / 67 | report section 15.2 | 1.00 | agree |
| first size with session repeats | 73 (25:75), 109 (50:50) | 111 (25:75), none | report section 15.2 | **0.66** | **explained, not a discrepancy**: a joined first session ends sooner, so the chain consumes more of the 164-session pool. It is a consequence of D101 and is reported in both the plan and section 16.2 |
| D2 batch accounting | 90 tok/img + 31 header once | 90 tok/img + 31 header once | StudyRH4, `data_sources.d2_batch_tokens` | 1.00 | agree; the preload uses the same function and carries the header as the session's first holding |
| emulator p99 lateness at 64 devices, mode A / B | 0.169 / 0.163 ms | 0.216 / 0.165 ms | report section 10.1 | 0.78 / 0.99 | agree |
| emulator CPU fraction at 64 devices, A / B | 0.55 % / 0.89 % | 0.7 % / 0.9 % | report section 10.1 | 0.79 / 0.99 | agree |

No disagreement above 2x anywhere.

**2. Physical plausibility.** Nothing here measures model latency or throughput, so no rate can be
faster than a committed curve. The only rates are the harness's own: 25,307 and 44,603 scheduled
actions in 180 s at under 1 % of a core, which is 0.04 ms of emulator CPU per action, in line with
the committed 10.1 run; and 0.13 to 0.24 s of CPU per AP difference at n = 1,000, which is 0.13 to
0.24 ms per bootstrap replicate over 120 to 237 plays. The **preload charges no uplink time by
decision (D101)**, so it must not be read as a transfer that happened implausibly fast: the frames
were on cloud-side disk before the clock started, and the emulator asserts the preload never
enters an uplink queue.

**3. Distribution sanity.** Spreads are reported next to every median: preload tokens 0 to 21,721
per device; join offsets 1.3 s to 258.4 s; pooled counts per seed differ at nearly every size
(for example 50:50 at 16 devices: 44 / 43 / 34 over seeds 1 / 2 / 3). **One constant was chased
down:** the pooled count at the entry point is exactly 23 at all three reported seeds and at all
three ratios. Two different causes, both checked: across **ratios** it is exact by construction -
the robot side depends only on the seed and the robot index, never on the ratio, so a fleet with 4
robot devices is the same robot experiment at 25:75, 50:50 and 75:25 - and across **seeds** it is
a coincidence of the total, not a short circuit, because the per-device breakdown differs
(7 / 3 / 5 / 8 at seed 1, 6 / 4 / 6 / 7 at seed 2, 5 / 7 / 7 / 4 at seed 3, over 10 / 10 / 8
session plays). Seed 0 gives 20 on the same sizes.

**4. Definition audit.** Three definitions to flag, one of them a genuine name reuse:

- **"pooled robot questions per run" now means something different, by decision.** Before D101 it
  was every annotated question in the chained sessions inside the run; under D101 it excludes the
  questions before the join point. Same name, new definition, authority D101. Any comparison of a
  pre-D101 count with a post-D101 count must say which it is, which is why both tables are kept on
  disk and the recomputed one is labelled.
- **"the first holding of a session"**: the object that carries the D2 header once. For a joined
  first session that is the **preload**; for every later session it is the **first batch**. The
  tests assert this rather than assuming it.
- unchanged: win-10 and sum-80 do not appear here; a "turn" is still the 0.5-s decision instant
  (StudyCTRL1c); 20 pooled questions (D82) and 200 dashcam instants (D71) are the same minima.

**5. Claim linkage.** Nothing here bears evidence on any claim. The instrument bears on **C5**
(joint representation x placement x timing beats decomposed policies under a quality SLO), which
round 1 is an early check of, and D101's purpose connects to **C4** (physical inertia, warm-append
versus cold re-prefill): without a part-way join no arm ever faced a prefix it had not watched
being built, so the cost C4 is about could not enter a policy comparison. **Measuring that is the
H100 runs' job, not this section's**, and no number here supports or weakens either claim. Nothing
measured here is scoped out by `research/FORMULATION.md`.

**6. Proxy validity.** Two proxies, both pre-existing and both still labelled: the **E10a median
frame size** stands in for a distribution, which D103 (h) now confines to flash tests and the
scorer refuses for a measured run; and the **D87 device answers** were produced by the 4B on the
A6000 / H100, not the Orin, so they are valid for ordering and first-order value only. One new
object is **not** a proxy and should not be read as one: the preload's `est_tokens` is the fleet's
own D2 accounting of the frames before the join, the same accounting as every batch, and the
engine's actual prompt token count is whatever it reports.

### 16.8 Open issues

1. **The robot run-time stagger is gone, and D101 does not say so in those words.** D101 puts the
   preload at `t = 0`, which a device that has not yet registered cannot send, so robots now
   register and start their first session at t = 0 and the join draw is their only per-device
   offset. Dashcam devices keep the run-time stagger (D101 says so explicitly). If the user meant
   robots to carry both offsets, it is a one-line change and the eligibility table has to be
   recomputed again.
2. **"The 7 GPU baselines" of D103 (f) is read as the seven non-policy arms of D65 as corrected by
   D90** - `device-only`, `always-cloud-fcfs`, `edf`, `edf-piece1024`, `edf-piece2048`,
   `utility-per-cost`, `b9` - which is the count the plan's own multiplicity paragraph uses. One of
   the seven, `device-only`, sends nothing and is scored from the recordings with no GPU run at all
   (D65), so a stricter reading of "GPU baselines" would make the family six comparisons wide. The
   scorer's `GPU_BASELINES` carries the seven-arm reading; changing it is one line.
3. **The PRIMARY label depends on fields no fleet-side code writes.** `classify_family` needs the
   run header to record the memory setting (it looks for `memory`, `memory_setting`, `kv_memory`,
   `memory_label`), the ratio and the mode, and the two **break sizes** must be passed in from the
   pilot. With any of them missing the comparison is EXPLORATORY and the output says which field
   was absent. The coordinator session owns the run header, so the field name has to be agreed
   before block 1 or every comparison will be labelled exploratory.
4. **D105's file format is this scorer's reading, not a committed schema.** The scorer expects
   `folds = {n_folds, by, assignment: {clip: fold}, maps: {fold: {tier: {a, b}}}}`, where
   `maps[k]` is the map fitted with fold k **held out**, so a clip in fold k is scored with
   `maps[k]`. D105 fixes the protocol, not the field names. Whoever produces the refit on the H100
   must write this shape, or the scorer will refuse the file - which is the intended failure, but
   it should be agreed first rather than discovered then.
5. **The D97 entry points are unchanged at 5 / 8 / 14, but the seed that binds has changed**, and
   seed 0's entry points now coincide with the reported seeds'. Amendment 2's claim that the pilot
   seed is systematically the strictest is **no longer true** and is corrected in section 16.2; the
   rule itself is untouched. These entry points are recomputed under D101; design-log row pending (planner will log as D107).
6. **Session repeats now begin at 73 devices at 25:75 and 109 at 50:50**, earlier than before D101,
   because a joined first session ends sooner. D84 says repeats are allowed but are not independent
   samples; at the top of the ladder this is now a slightly larger caveat than amendment 2 recorded.
7. **The coordinator must store a preload as cold history for the fairness digest to mean
   anything.** A's `coordinator.py` and `cstate.py` already carry `history_preload` ingestion and
   A's digest coverage matches mine, but no end-to-end cell has been run against the real
   coordinator with a D101 trace; that is the pre-pilot H100 order of D104, not flash work.
8. **Open issues 3 to 11 of section 13 and 15.6's statement stand**, except where this section
   corrects them: amendment 1's open issue 3 (the run-time reading of the stagger) is **closed by
   D101** for robots and kept for dashcams, and open issue 8 (the two CHOICE items) is **closed by
   D103**. The rest - the interpolated device recall latency, the missing dense calibration refit,
   Part 2 not having run, the median frame size, multiplicity, the session pool at 25:75 - are
   unchanged.
9. **Nothing in this section is a finding, and no sweep was run.** The live mechanism verification
   and the live consistency check belong to the H100 runs; section 16.6 and 16.7 are the
   flash-scope instances and do not discharge them.

### 16.9 Files created or changed in StudyLIVE2-fix

Created:

- `results/orchestration/live2/fleet/eligibility_join/robot_eligibility_4_to_128.csv` (1,500 rows)
- `results/orchestration/live2/fleet/eligibility_join/robot_eligibility_summary.json`
- `results/orchestration/live2/fleet/scale_64_join/` (trace, both mode runs, `scale_summary.json`)

Changed:

- `experiments/orchestration/live2/fleet/trace.py` (D101: the join draw, the preload, the batch
  grid, the question filter, the stats, the digest row, `JOIN_FRAC_MAX`, the docstring)
- `experiments/orchestration/live2/fleet/events.py` (`history_preload` in `FIELDS`)
- `experiments/orchestration/live2/fleet/emulator.py` (the preload path, charging no uplink, the
  run-header counters, the digest docstring)
- `experiments/orchestration/live2/fleet/eligibility.py` (the D101 columns and the per-ratio
  preload summary; the "row pending" wording dropped)
- `experiments/orchestration/live2/fleet/data_sources.py` (`calibration()` parses D105 folds)
- `experiments/orchestration/live2/scorer/score.py` (D103 (e), (f), (h); D105 `map_for` and the
  FINAL-map refusal; D101 `history_preload`; D99 diagnostics; `is_measured_run`,
  `calibration_use`; the docstring)
- `experiments/orchestration/live2/fleet/tests/test_live2_fleet.py` (234 checks)
- `results/orchestration/live2/ANALYSIS_PLAN.md` (header APPROVED; the D103 rulings through the
  index, the eight-item prose, sections 2, 3, 3.1, 4.1, 5, 7, 9, 10; D99 and D105 added; the
  recomputed tables; the change log)
- `reports/study_live2_fleet.md` (this section)

Not touched: `live2/schema.py`, `live2/CONTRACT.md` and everything else on the coordinator side;
`research/policy_design_log.md`, `research/policy_spec_v4.md`, `research/policy_ablations.md`,
`research/EXPERIMENTS.md`, `research/STATUS.md`, `results/INDEX.md`. Read-only git only; no H100,
no GPU, no model download; the StudyD15 frames were neither moved nor deleted.
