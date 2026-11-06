# Dataset download: RTV-Bench, HERBench, OVO-Bench, StreamingBench

This file has no flash section yet. Flash's results (its `results/datasets/download_manifest.json` and its own section) were not on `origin/main` when the H100 copy was made, so flash's section is to be added from flash.

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
