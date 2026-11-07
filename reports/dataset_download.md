# Dataset download: RTV-Bench, HERBench, OVO-Bench, StreamingBench

Flash's section was added from flash on 2026-11-06 (see § flash below); it was not on `origin/main` when the H100 copy was made. The H100 section below is unchanged.

## H100 (h100nvl, sn4622120321): copy of flash's datasets, 2026-11-05

**Status:** partial by disk limit.
- OVO-Bench (source videos) and RTV-Bench are complete and verified.
- HERBench and StreamingBench have annotations, metadata and code only. Their videos do not fit on this disk.
- No experiment, transcoding, chunking, clip preparation, rendering or inference was run.

**Summary:** `results/datasets/download_manifest_h100.json`.

### How the data was obtained (deviation from the original request)
- **Not downloaded from Hugging Face.** The prerequisite manifest (`results/datasets/download_manifest.json`) was missing on `origin/main`, so the HF download was stopped. On the user's instruction the four datasets were then copied from flash's read-only share instead (`fmnet-flash:/mnt/ssd/hf_models/datasets`, with `~/.local/bin/fmpull`: rsync `--partial --append-verify`, resumable, never deletes).
- **Reference used in place of the committed manifest:** flash's own files, pulled to `/home/pragya/data/flash/meta/` and kept unchanged:
  - `preflight.json`: flash's HF listing at the pinned commits, with sizes and LFS sha256.
  - `annotations_report.json`, `archives.json` and the logs.
  - Flash's per-dataset `ffprobe.jsonl`.
- **Code repos** were copied from flash's clones (with `.git`), not freshly cloned. Their HEAD commits are listed below.
- **Free-space floor:** the user lowered it from 130 GB to 20 GB. Free space after the copy is 38 GB.
- **Layout:** flash's layout is kept under `/home/pragya/data/datasets/<dataset>/` (`hf/`, `code/`, `src_videos/`, `logs/`, `ffprobe.jsonl`). Archives are kept, and nothing was renamed, filtered or deleted.

**Scripts** (`experiments/datasets/`):

| script | purpose |
|---|---|
| `pull_from_flash.sh` | pulls the paths in a list file, logging to `logs/datasets_pull.log`; per-path free-space and latency-marker checks |
| `extract_ovo.sh` | extracts the OVO-Bench archives |
| `verify_annotations.py` | annotations, counts and code check |
| `verify_archives.sh` | archive part hashes and tar listing |
| `ffprobe_compare.py` | ffprobe (and hash) comparison against flash |
| `d7b_gate.sh` | pauses pulls while StudyD7b runs |

### Per dataset

| dataset | HF revision (= flash) | code repo @ commit | local size | questions | unique videos | videos here | ffprobe failures |
|---|---|---|---|---|---|---|---|
| OVO-Bench | `JoeLeelyf/OVO-Bench` @ `fec29e33` | JoeLeelyf/OVO-Bench @ `c34093f9` | 92.7 GB | 3,035 (1,640 entries: 1,468 backward + 1,567 forward sub-queries) | 644 | 645 mp4 (extracted) | 0 |
| RTV-Bench | `RTVBench/RTV-Bench` @ `62ec75f8` | LJungang/RTV-Bench @ `a928cbe8` | 101.1 GB | 4,608 | 552 | 552 mp4 | 0 |
| HERBench | `DanBenAmi/HERBench` @ `30b42e97` | DanBenAmi/HERBench @ `fe66f377` | 59 MB | 27,631 (lite 2,000 / 68 videos; lite_v2 1,971 / 68 videos) | 335 | not pulled | — |
| StreamingBench | `mjuicem/StreamingBench` @ `48872fa7` | THUNLP-MT/StreamingBench @ `89299232` | 85 MB | 4,500 | 901 | not pulled | — |

- The question and video counts use flash's definitions. StreamingBench totals exclude `Proactive_Output_50.csv` (50 rows), as flash's 4,500 / 901 imply.
- The OVO-Bench 645 mp4 against 644 annotated videos is the same on flash.

### Checks
1. **Revisions.** The four HF commits recorded by flash are also the current HF heads (queried 2026-11-05). Every pulled HF metadata file was checked against HF's record at that commit, by size and git blob sha1, plus sha256 for LFS files: 2 + 3 + 19 + 18 files, **0 mismatches**.
2. **Annotations.**
   - Hashes are recorded in the manifest (`annotation_sha256`).
   - Question counts, entry counts and the unique-video-ID **sets** equal flash's `annotations_report.json` for all four datasets.
3. **Code.** All four clones pass `git fsck`, have clean work trees, and point at the four GitHub repos named by the user.
4. **OVO-Bench archives** (`hf/src_videos.tar.parta[a–e]`, 46.3 GB; `chunked_videos.tar.part*` excluded):
   - All 5 parts match the HF LFS sha256.
   - `tar -t` on the joined parts: exit 0, 660 members (flash: 660), 645 regular files.
   - Extracted to `ovo_bench/src_videos/` (flash's layout): 645 mp4.
5. **RTV-Bench videos.** All 552 mp4 match the HF LFS sha256 at the pinned commit.
6. **HERBench published checksums** (`videos.tar.checksums.txt`): the file was pulled and matches HF. The 17 parts it covers were not pulled, so it was not run here (flash's `herbench_fix.log` reports all 17 OK).
7. **ffprobe** (ffprobe 4.4.2, every video, one low-priority process): 0 failures in both datasets (flash: 0).
   - Size, width, height, codec and audio-stream count match flash for every video.
   - fps matches for every video once flash's definition is used (`r_frame_rate` rounded to 3 decimals).

### Differences from flash (reported, not resolved)
- **Duration** differs on 231 / 645 OVO-Bench videos (largest gap 0.032 s) and 345 / 552 RTV-Bench videos (largest gap 0.130 s; 5 above 0.1 s).
  - Flash's values match neither one ffprobe field here: neither the first video stream's duration nor the container duration matches all of them.
  - The video bytes are identical to the published files (RTV-Bench by per-file sha256; OVO-Bench by archive sha256 and the identical tar listing), so the difference lies in how duration was read, not in the content.
  - Flash's ffprobe version is not recorded in the pulled files, so the cause is **not confirmed**.
- **HERBench and StreamingBench videos are absent here** (flash: about 378 GB and about 538 GB, including flash's extracted folders). They do not fit on this disk with a 20 GB floor.
- **Flash's StreamingBench share contains a folder named `extracted_flat_INCORRECT/`.** Only annotations and code were pulled for StreamingBench, so it was not copied.

### Access
- No gated or blocked access.
- No Hugging Face login or token was used. All metadata queries were anonymous.

### Overlap with StudyD14-trace / StudyD7b
- All pulls, extraction and checks ran 16:06–16:49 while StudyD14-trace ran its batched 32B N = 9 arm on GPU 2. That arm is accuracy only, with no latency measured. The data jobs used CPU, disk and network only, at nice 19 / idle IO priority.
- Nothing will run during StudyD7b: all dataset work finished at 16:49, before StudyD14-trace's last arm ended. A queue gate (`experiments/datasets/d7b_gate.sh`) sets `~/.fmnet_latency_active` and stops any remaining `dl*` session before D7b starts.


---

## flash (RTX 3090 Ti / A6000): original download and verification, 2026-11-04

Data preparation only. No inference, no model loading, no GPU. This report selects no
dataset and tests no hypothesis.

Data lives outside the repo at `/mnt/ssd/hf_models/datasets/<name>/`.
`/mnt/ssd` itself is owned by another user and is not writable, so `/mnt/ssd/datasets`
could not be created; the writable `/mnt/ssd/hf_models/` was used instead, on the same
filesystem. Flagged rather than worked around.

**Status: COMPLETE.** All four datasets downloaded, extracted and verified. No inference
was run and neither GPU was touched.

---

### 1. Results

#### 1.1 Summary

| dataset | repo @ SHA | downloaded | videos | questions | ffprobe fail | size mismatch | archives | status |
|---|---|---|---|---|---|---|---|---|
| RTV-Bench | `RTVBench/RTV-Bench` @ `62ec75f8cd7c` | 101.1 GB | 552 | 4,608 | 0 | 0 | n/a | **PASS** |
| HERBench | `DanBenAmi/HERBench` @ `30b42e97180f` | 170.8 GB | 334 | 27,631 | 0 | 0 | 1/1 ok | **PASS** |
| OVO-Bench | `JoeLeelyf/OVO-Bench` @ `fec29e338574` | 46.3 GB | 645 | 3,035 | 0 | 0 | 1/1 ok | **PASS** |
| StreamingBench | `mjuicem/StreamingBench` @ `48872fa70712` | 202.6 GB | 900 | 4,500 | 0 | 0 | 21/21 ok | **PASS** |

Totals: 637 files, 520.8 GB downloaded, **0 size mismatches** against the pinned Hugging Face
metadata, **2,431/2,431 videos pass ffprobe**, **23/23 archives pass** integrity tests.
None of the four repos is gated; an existing login (`psharma05`) was used and no token was
printed, logged or written.

Code repos cloned and pinned:

| dataset | code repo | SHA |
|---|---|---|
| RTV-Bench | `LJungang/RTV-Bench` | `a928cbe82b11fd7be7c6f7c0a40c662427ec40d7` |
| HERBench | `DanBenAmi/HERBench` | `fe66f377fd4a4a1689b97837129edbaacd489ebe` |
| OVO-Bench | `JoeLeelyf/OVO-Bench` | `c34093f9a072d93f9e1c6b923446dfba71f4528e` |
| StreamingBench | `THUNLP-MT/StreamingBench` | `89299232c4cc1cc3721951173c5f107b48cf6877` |

#### 1.2 ffprobe

Every video probed; no failures and no repairs attempted. Per-video records (path, duration,
resolution, fps, codec, audio-stream count) are in
`/mnt/ssd/hf_models/datasets/<name>/ffprobe.jsonl`.

| dataset | probed | ok | duration min / median / max (s) | total | codecs | top resolutions |
|---|---|---|---|---|---|---|
| RTV-Bench | 552 | 552 | 127.8 / 523.3 / 11,087.9 | 167.2 h | h264 533, vp9 11, av1 8 | 852×480 (255), 480×360 (158) |
| HERBench | 334 | 334 | 28.4 / 180.0 / 4,485.1 | 48.8 h | h264 256, mpeg4 77, vp9 1 | 1408×1408 (154), 1920×1080 (107) |
| OVO-Bench | 645 | 645 | 6.0 / 308.0 / 9,047.1 | 85.2 h | h264 434, vp9 163, mpeg4 48 | 1280×720 (281), 1920×1080 (105) |
| StreamingBench | 900 | 900 | 120.7 / 605.3 / 1,389.3 | 145.9 h | h264 880, hevc 20 | 1920×1080 (439), 1280×720 (43) |

HERBench's measured total of 48.8 h agrees with the 48.76 h stated in its own
`data/video_metadata.json`, which is an independent check that the full archive extracted.

503 `__MACOSX/._video.mp4` AppleDouble stubs inside the StreamingBench zips are not videos
and are excluded from these counts rather than reported as failures.

#### 1.3 Archive integrity

| archive | parts/members | result |
|---|---|---|
| HERBench `videos.tar` (17 parts) | 334 members | ok |
| OVO-Bench `src_videos.tar` (5 parts) | 660 members | ok |
| StreamingBench, 21 `.zip` | CRC-tested, no bad member | 21/21 ok |
| RTV-Bench | ships no archive (plain `.mp4`) | n/a |

HERBench's published `videos/videos.tar.checksums.txt` was verified with `sha256sum -c`:
**all 17 parts OK** (exit 0). The 334 tar members equal the 334 extracted videos.
RTV-Bench, OVO-Bench and StreamingBench publish no hashes.

#### 1.4 Question-to-video cross-check

| dataset | questions | videos referenced | videos on disk | questions whose video is missing | videos with no question |
|---|---|---|---|---|---|
| RTV-Bench | 4,608 | 552 | 552 | **0** | **0** |
| HERBench | 27,631 | 335 | 334 | **65** | 0 |
| OVO-Bench | 1,640 entries | 644 | 645 | **0** | 1 |
| StreamingBench | 4,500 | 901 | 900 | 502 (see below) | 100 (see below) |

Observations:

- **HERBench is missing one video.** `PersonPath22/uid_vid_00109.mp4` appears in
  `videos/video_list.txt` (335 lines) but is not a member of the published tar, and 65
  questions reference it. Every part's sha256 matches the published checksums, so the archive
  is exactly as released: the file is absent upstream. Not repaired, not substituted.
- **OVO-Bench has one unreferenced video**, `030-hm3d-RJaJt8UjXav.mp4` (645 on disk vs 644
  referenced).
- **StreamingBench's 502/100 are label mismatches, not missing data.** Three naming
  inconsistencies between `question_id` prefixes and the zip/directory names account for all
  of them; after mapping, nothing is absent:

  | `question_id` prefix | zip / directory | videos | questions |
  |---|---|---|---|
  | `Misleading Context Recognition` | `Misleading Context Understanding` | 50 (sample sets verified identical) | 250 |
  | `Sequential_Question_Answering` (underscores) | `Sequential Question Answering` (spaces) | 50 | 250 |
  | `Active Output_sample_2` | `Proactive Output/sample_2` | 1 | 2 |

  The `Sequential_Question_Answering.csv` file is internally inconsistent: its `task_type`
  column uses spaces while its `question_id` prefix uses underscores. No file was renamed to
  reconcile any of this; the mapping is recorded in `results/datasets/crosscheck.json`.

#### 1.5 Counts against upstream claims

Reported, not reconciled.

| dataset | quantity | ours | upstream claim(s) | difference |
|---|---|---|---|---|
| RTV-Bench | videos | 552 | 552 | **0** |
| RTV-Bench | QA pairs | 4,608 | 4,631 (paper) / 4,608 (README) | 0 vs README; **−23** vs paper |
| HERBench | videos | 334 extracted (335 listed) | 335 (README) / 337 (CITATION.cff) | **−1** vs README; **−3** vs CITATION |
| HERBench | questions | 27,631 | 27,936 (README) / 26,806 (CITATION.cff) | **−305** / **+825** |
| HERBench | Lite questions | 2,000 | 5,960 | **−3,960** |
| HERBench | Lite-v2 questions | 1,971 over 68 videos | 1,971 over 68 videos | **0** |
| OVO-Bench | videos | 645 on disk, 644 referenced | 644 | **+1** on disk |
| OVO-Bench | queries | 3,035 | 2,814 (paper) / 3,100 (README) | **+221** / **−65** |
| StreamingBench | videos | 900 | 900 | **0** |
| StreamingBench | QA pairs | 4,500 | 4,500 | **0** |

Notes on how ours were counted:

- **OVO-Bench 3,035** is derived, not a row count. The annotation file holds 1,640 entries;
  1,468 are single-query, and the three streaming tasks (REC 82, SSR 42, CRR 48 entries)
  carry `test_info` arrays totalling 1,567 timed sub-queries. 1,468 + 1,567 = 3,035. Which
  convention the paper's 2,814 and the README's 3,100 use is not stated.
- **StreamingBench 4,500** excludes `Proactive_Output_50.csv` (50 rows), which is a subset of
  `Proactive_Output.csv` (250 rows).
- **StreamingBench 900 videos** includes three files named `Active Output_{3,4,5}.mp4` rather
  than `video.mp4`, in `Proactive Output/sample_{45,48,50}`. Counting only `video.mp4` gives
  897.
- **HERBench Lite** ships 2,000 rows in `data/herbench_annotations_lite.json`; the README's
  5,960 and `videos_lite_info.txt`'s "~5,600 questions" both disagree with the file.

#### 1.6 Procedure notes

Two upstream packaging traps were hit and are recorded because they silently lose data:

1. **HERBench's `videos.tar` is a nested split.** `videos/videos_lite_info.txt` documents that
   parts 00–03 form a complete Lite archive (~34.33 GB, ~67 videos) inside the full 00–16 set,
   so its end-of-archive marker sits mid-stream. A plain `tar -xf` stops there, extracts 68
   videos and exits 0. `tar -xif` (`--ignore-zeros`) is required. The 68-video tree is kept at
   `extracted_lite_subset_00-03/` and excluded from all counts as a strict subset.
2. **StreamingBench's zips share one namespace.** Every zip contains `sample_N/video.mp4`, so
   unzipping them into a single directory overwrites across tasks. Upstream `README.md:76-84`
   directs the non-`real` zips into one `omni/` folder, but six of those tasks each ship
   `sample_1..50`; following that literally would overwrite about 250 videos. Extraction is
   therefore one directory per task under `extracted_by_task/`, which is lossless and still
   reducible to the upstream grouping. Nothing was renamed, filtered or re-encoded.

Not run, per the task: RTV-Bench's `0_transcode_raw_videos_overwrite.sh` and every other
transcode, chunking, clip-preparation, frame-rendering and inference script. OVO-Bench's
`chunked_videos.tar.part*` (153.3 GB) was not downloaded. No third-party or YouTube source
was fetched.

Concurrent load on the host during the run, reported and not interfered with: another user's
four `CarlaUE4-Linux-Shipping` processes and an `ollama` `llama-server` on GPU 1 (A6000, 100%
utilisation), and this user's `cadet` acceptance-matrix job in Docker. No latency experiment
was running on flash at any point, which was checked before the download started. GPU 0
(RTX 3090 Ti) was idle. This job used neither GPU.

---

---

### 2. Temporal field semantics

The earlier field-name table recorded which field *names* exist. A missing name does not
show a property is missing, so each field below was traced to upstream code, README or
paper. Every meaning carries a source. Where no source settles it, the value is UNKNOWN
and is written as UNKNOWN rather than inferred from the field name.

Counts regenerate via `experiments/datasets/temporal_field_semantics.py` into
`results/datasets/temporal_field_semantics.json`.

#### Corrected table

Changes against the earlier field-name table are marked **CORRECTED**.

| field | RTV-Bench | HERBench | OVO-Bench | StreamingBench |
|---|---|---|---|---|
| query timestamp | **CORRECTED — `end_time`** | — | `realtime`; `ask_time` (CRR) | `time_stamp` |
| answer timestamp | — | — | — | `ground_truth_time_stamp` (Proactive only) |
| evidence interval | **CORRECTED — none** | `metadata.required_timestamps` (UNKNOWN meaning) | `start_times`/`end_times` (REC); `start_time`/`end_time` (SSR); `clue_time` (CRR) | — |
| event onset | — | **CORRECTED — removed, UNKNOWN** | `start_times` (REC); `start_time` (SSR) | `ground_truth_time_stamp` (Proactive only) |
| multiple answers over time | **CORRECTED — PRESENT** | — | `test_info[]` (REC/SSR/CRR) | — |
| task category | `type`, `field` | `task_type` | `task` | `task_type` |

Three corrections, all against our own earlier reading, not against upstream:

1. **RTV-Bench `start_time`/`end_time` are not an evidence interval.** `start_time` is
   `0` in all 4,608 rows, and the eval path never reads it. `end_time` is the query
   timestamp.
2. **RTV-Bench does have multiple answers over time.** It is expressed as separate rows
   linked by a group token inside `questionID`, not as a nested array, which is why a
   field-name scan missed it.
3. **HERBench "event onset" is withdrawn.** Nothing upstream defines
   `required_timestamps`, so its meaning is UNKNOWN and no onset reading is supported.

#### RTV-Bench

`end_time` — **query timestamp**; the clip handed to the model is `[0, end_time]`.
`scripts/utils/video_utils.py:177-187` builds it with `ffmpeg -ss 0 -t <end_time>`, and
`scripts/infer/infer_model_rtv.py:101,107` is the only eval caller, passing
`end_time=float(sample["end_time"])`. `README.md:122-127`: "RTV-Bench evaluation operates
on **video clips** rather than raw long videos ... split according to the provided
timestamps".

`start_time` — constant `0` across all 4,608 rows (one distinct value). Read only by
`scripts/data_preparation/prepare_rtv_clips.py:128-157`, an optional clip-prep path that
cuts `[start_time, end_time]`; since `start_time` is always 0 that is the same
`[0, end_time]` prefix. It carries no per-question information.

So the pair is **the clip given to the model**, not evidence for the answer, and not a
query window in the sense of a bounded interval.

**Recurrence.** `README.md:38` states the design intent directly: "**Multi-Timestamp
Question Answering**: answers evolve as video content changes over time."

| grouping | groups | groups with >1 row | of those, answer changes |
|---|---|---|---|
| (video, normalized question text) | 2,889 | **1,116** | **1,102** |
| `questionID` group token | 1,011 | 1,010 | **1,010** |

Rows per group — by text: `{1: 1773, 2: 703, 3: 233, 4: 171, 5: 8, 6: 1}`;
by id-group: `{1: 1, 2: 3, 3: 20, 4: 597, 5: 212, 6: 160, 7: 11, 8: 7}`.

**Linking IDs.** `questionID` has the form `q-group-<token>-<question_index>-option<N>`
and parses for 4,608/4,608 rows. The token is the hierarchy that links rows: 1,011
distinct tokens, **0 of which span more than one video**. Rows sharing both a token and
a `question_index` are the same question re-asked at a different `end_time`.

Three complete example groups are in
`results/datasets/temporal_field_semantics.json` under `rtv_bench.examples`. The
clearest is `q-group-u1yjsiyl5` (video `SportsCam_010.mp4`, type `Event-PU`), where
"What happened at this moment?" appears at `end_time` 74.6 / 146.95 / 153.68 / 657.74
with answers A / D / C / B against an identical option list.

#### OVO-Bench

`realtime` — **query timestamp**. `utils/chunk_videos.py:30,39`:
`end_time = math.ceil(data[i]["realtime"])`, `clip = video.subclip(0, end_time)`. The
model sees `[0, realtime]`. Consumed at `utils/OVOBench.py:30` (backward) and `:62`
(realtime).

`test_info[].realtime` — the query timestamp of each successive probe of the same item;
`utils/chunk_videos.py:46,56` chunks `[0, realtime]` per probe, and
`utils/OVOBench.py:93-105` loops `test_info` writing one response per probe.

`ask_time` (CRR) — the time the question is posed. `clue_time` (CRR) — **the time from
which the answer becomes supported by the video**. `utils/OVOBenchScore.py:67` sets
`gt = "No" if test_info_["type"] == 0 else "Yes"`, and `type` tracks `clue_time` exactly:

| CRR check (n=48) | result |
|---|---|
| `type == 0` iff `realtime < clue_time` | **48/48**, 0 violations |
| `ask_time < clue_time` | **48/48** |
| `ask_time == min(test_info.realtime)` | **48/48** |

So yes: `clue_time` marks when the answer becomes supported, and `ask_time` is a query
time strictly before it in every entry — the question is always posed while still
unanswerable, and the first probe is at `ask_time`.

`start_times`/`end_times` (REC) — intervals of each occurrence of `activity`.
`start_time`/`end_time` (SSR) — intervals of each tutorial step, parallel to `all_steps`.

**How `test_info` changes the correct answer over time.** REC: each probe carries
`count`, the running number of occurrences visible by that time, scored at
`utils/OVOBenchScore.py:52` via `get_score_REC(response, test_info_["count"])` — the
ground-truth count rises as the video advances. SSR: each probe carries `type`, flipping
the yes/no ground truth for the step in question (`:59`). CRR: as above (`:67`).

Field presence per task (entries / sub-queries):

| task | entries | realtime | ask_time | clue_time | start_times | end_times | start_time | end_time | test_info | sub-queries |
|---|---|---|---|---|---|---|---|---|---|---|
| ACR | 109 | 109 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ASI | 148 | 148 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ATR | 116 | 116 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| CRR | 48 | 0 | 48 | 48 | 0 | 0 | 0 | 0 | 48 | 240 |
| EPM | 297 | 297 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| FPD | 101 | 101 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| HLD | 186 | 186 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OCR | 149 | 149 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OJR | 184 | 184 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| REC | 82 | 0 | 0 | 0 | 82 | 82 | 0 | 0 | 82 | 698 |
| SSR | 42 | 0 | 0 | 0 | 0 | 0 | 42 | 42 | 42 | 629 |
| STU | 178 | 178 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

One example per task is in the JSON under `ovo_bench.per_task.<task>.example`.

#### HERBench

`metadata.required_timestamps` — **UNKNOWN**. The literal string does not occur anywhere
in the upstream code repo (`DanBenAmi/HERBench @fe66f377`), and neither `README.md` nor
`USAGE_GUIDE.md` defines it. Only its on-disk shape can be stated.

**MRFS does not use it.** MRFS (Minimum Required Frame Set) is computed by re-querying the
model over frame counts chosen by a frame selector — `evaluation/calculate_mrfs.py:68-74`
(text-only correct → MRFS 0; wrong at full context → undefined), `:218` `'mrfs': best_k`,
with selectors in `evaluation/frame_selectors/{uniform,vanila_blip_similarity}.py`. No
annotated timestamp enters that computation, so there is no oracle-frame path keyed on
`required_timestamps` in the released code.

Accordingly **"event onset" is removed** from HERBench's row: no source supports it.

Populated fraction — full **20,919/27,631 = 0.757**; Lite-v2 **1,491/1,971 = 0.756**.
Two task types account for every absence, in both splits:

| task_type | full n | full frac | lite_v2 n | lite_v2 frac |
|---|---|---|---|---|
| Action Counting | 2,040 | 1.00 | 144 | 1.00 |
| Action Sequence Integrity Identification | 2,212 | 1.00 | 154 | 1.00 |
| Appearance-Grounded Attribute Recognition | 875 | 1.00 | 32 | 1.00 |
| Appearance-Grounded Behavior & Interactions | 1,222 | 1.00 | 87 | 1.00 |
| Appearance-Grounded Localization & Trajectory | 2,360 | 1.00 | 182 | 1.00 |
| False Action Memory | 2,276 | 1.00 | 158 | 1.00 |
| False Object Memory | 2,310 | 1.00 | 159 | 1.00 |
| Multi-Entities Grounding and Localization | 2,922 | 1.00 | 231 | 1.00 |
| Multi-Person Duration Reasoning | 2,564 | 1.00 | 196 | 1.00 |
| Region Localized People Counting | 2,138 | 1.00 | 148 | 1.00 |
| **Scene Verification & Arrangement** | 4,568 | **0.00** | 328 | **0.00** |
| **Temporal Shot Ordering** | 2,144 | **0.00** | 152 | **0.00** |

Three incompatible encodings coexist, which is itself a reason not to infer a meaning:

| form | full | lite_v2 |
|---|---|---|
| list of `'M:SS:mmm'` (points) | 8,838 | 615 |
| single string `'MM:SS-MM:SS'` (one interval) | 6,595 | 449 |
| list of `'HH:MM:SS.mmm - HH:MM:SS.mmm'` (intervals) | 5,486 | 427 |
| absent | 6,712 | 480 |

Timestamps per question, list forms only — full: min 1, max 63, median 4
(histogram `{4: 4848, 2: 2892, 3: 2694, 25: 848, 1: 591, 24: 544, 23: 313, 5: 222, ...}`);
Lite-v2: min 1, max 11, median 3.

Note `README.md:35` states the benchmark's design target — "each question requires
aggregating at least **k ≥ 3 distinct, temporally separated visual cues**" — and
`:41` reports "Mean MRFS ~5.5". Neither sentence defines `required_timestamps`, so
neither is treated as a source for it.

#### StreamingBench

`time_stamp` — **query timestamp**; the clip handed to the model ends here.
`src/benchmark/StreamingBench.py:41-50` converts it to seconds and calls
`split_video(video_path, time_start, timestamp)` with `time_start = 0` unless a context
window is configured; `src/utils/video_execution.py:4,23-25` runs ffmpeg with
`ss=start_time, t=end_time-start_time`.

`ground_truth_time_stamp` — Proactive_Output only: **the time at which the model is
expected to emit `ground_truth_output`**. `src/benchmark/StreamingBenchProactive.py:35-50`
polls the model once per second from `time_stamp + 1` to
`max_time = ground_truth_time + 4`; `src/data/count.py:43-57` scores a hit when the
output lands within ±2 s of `ground_truth_time`.

Coverage: `Proactive_Output.csv` 250/250 rows populated over 51 stripped video ids;
`Proactive_Output_50.csv` 50/50 over 1. No other file has the column.

**The 901.** Within the single video `sample_2` of `Proactive_Output.csv`, the five
question ids do not share a prefix:

```
Proactive Output_sample_2_1    ts=00:00:01  gt_ts=00:00:12
Active   Output_sample_2_2     ts=00:00:35  gt_ts=00:00:57
Proactive Output_sample_2_3    ts=00:09:14  gt_ts=00:09:43
Proactive Output_sample_2_4    ts=00:11:48  gt_ts=00:12:07
Active   Output_sample_2_5     ts=00:12:29  gt_ts=00:12:46
```

Two rows read `Active Output` where three read `Proactive Output`. Stripping the trailing
question index therefore yields two ids — `'Proactive Output_sample_2'` (3 rows) and
`'Active Output_sample_2'` (2 rows) — for what the file otherwise treats as one video, so
the union across files is 901 where upstream claims 900. The other 49 Proactive videos
have 5 rows each under a single prefix. Reported only; no data was changed.

---

### 3. Licenses

Quoted statement and location for each of the three places a licence can appear. No legal
conclusion is drawn; conflicts are reported, not resolved.

#### RTV-Bench

| location | statement |
|---|---|
| HF dataset card | `RTVBench/RTV-Bench` `README.md:2` (YAML front matter) — `license: mit` |
| code repo LICENSE | **absent** — `LJungang/RTV-Bench @a928cbe8` ships no LICENSE or COPYING file |
| README | no licence section; no occurrence of "licen", "CC BY" or "non-commercial" |

Only one statement exists, so nothing conflicts. The code repo is unlicensed as published.

#### HERBench

| location | statement |
|---|---|
| HF dataset card | `DanBenAmi/HERBench` `README.md:4` — `license: cc-by-nc-sa-4.0` |
| HF LICENSE file | `LICENSE:1` — "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International Public License" |
| code repo LICENSE | `DanBenAmi/HERBench @fe66f377` `LICENSE:1` — "MIT License / Copyright (c) 2025 Dan Ben-Ami, Gabriele Serussi, Kobi Cohen, Chaim Baskin" |
| README | `README.md:328` — "This dataset is released under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)]"; `:333` — "HERBench is released strictly for **non-commercial** research and educational purposes."; `:334` — "The benchmark is constructed using videos originating from existing datasets and platforms, including WildTrack, HD-EPIC, PersonPath22, and publicly available online videos (e.g., YouTube trailers). All rights to the original video content remain with their respective owners and licensors." |

Consistent: data CC BY-NC-SA 4.0 (**non-commercial**), code MIT. The README additionally
disclaims rights over the underlying source videos.

#### OVO-Bench — **CONFLICT**

| location | statement |
|---|---|
| HF dataset card | `JoeLeelyf/OVO-Bench` `README.md:2` (YAML front matter) — `license: cc-by-sa-4.0` |
| code repo LICENSE | `JoeLeelyf/OVO-Bench @c34093f9` `LICENSE:1` — "MIT License / Copyright (c) 2024 Junbo Niu" |
| README | `README.md:112-113` — "## License / OVO-Bench is released under `CC BY-NC-SA 4.0` license. By downloading our dataset from our website or other sources, the user agrees to adhere to the terms of `CC BY-NC-SA 4.0` and licenses of the source datasets" |

The reported conflict is confirmed. The HF card says **CC BY-SA 4.0** (no NonCommercial
clause); the GitHub README says **CC BY-NC-SA 4.0** (NonCommercial). The two differ on
whether commercial use is permitted. Both are current as of the pinned SHAs. Reported
without resolution.

#### StreamingBench — **no data licence declared**

| location | statement |
|---|---|
| HF dataset card | `mjuicem/StreamingBench` `README.md` front matter has **no `license:` key** (keys present: `task_categories`, `language`, `size_categories`, `dataset_info`) |
| code repo LICENSE | `THUNLP-MT/StreamingBench @89299232` `LICENSE:1` — "MIT License / Copyright (c) 2021 THUNLP" |
| README | no licence section; no occurrence of "licen", "CC BY" or "non-commercial" |

The MIT LICENSE sits in the **code** repo and does not, on its face, speak to the video
data hosted separately on Hugging Face. The dataset therefore carries no stated licence
at the pinned SHA. Reported as a gap, not interpreted.
