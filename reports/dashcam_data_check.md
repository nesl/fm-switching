# Dashcam data check: Nexar (DoTA metadata only)

**E-id:** StudyD0-nexar (pre-registered 2026-11-04). **Host:** h100nvl, CPU and disk only. No GPU, no model, no rendering, no inference.
**Date:** 2026-11-04. All values below are computed from the files. Mismatches with expected values are reported as findings; nothing was adjusted.

## Summary

- **Nexar:** downloaded in full and size-verified (2,857 files, 31.38 GB). Every count on the dataset card matches: 2,844 rows, 1,500 train videos, 750/750 positive/negative. All 2,844 videos are 1280×720 H.264, and 0 are corrupt (full decode).
- **Timing matches the paper:** event − alert has mean 1.600 s and max 4.466 s (published: 1.6 and 4.5).
- **Footage around the event:** every train positive has at least 2 s of footage after `time_of_event`. 749/750 have at least 3 s before `time_of_alert`.
- **Not verifiable:** the metadata has no collision vs near-collision field, so the expected 400/350 split can't be checked.
- **Test splits use a different timebase:** test clips are about 10 s long, but their `time_of_event`/`time_of_alert` are in the original full video's timebase, not the clip's. See finding F3.
- **DoTA:** frames are unavailable. Both Google Drive links (full archive and split folder) returned HTTP 404 on 2026-11-04, so only the metadata checks were done. These match: 3,275/1,402 clips, 477,650 frames in metadata, 2,261 ego-5 clips.

## Decisions recorded 2026-11-04 (user)

- **Only Nexar training clips are used.** The test splits (test-public, test-private) are not used for anything.
- **Test-split timing fields are not used.** The timebase of their `time_of_event` / `time_of_alert` is **unresolved** (finding F3): the values appear to be in the source-video timebase, not the ~10 s clip's. Whatever the timebase, they are not used.
- **The metadata has no collision / near-collision field** (finding F1). The 400 / 350 split can't be reproduced from the files and is not used.
- **DoTA is not used.** Its frames were unavailable; going ahead with Nexar alone. Nothing is downloaded from YouTube.

## Sources, sizes and paths

| item | source | where | size |
|---|---|---|---|
| Nexar | HF dataset `nexar-ai/nexar_collision_prediction` (gated; access approved). Commit `7535d0656dac31d7da2846913bb69c6331d2a70a` (from the download cache metadata) | `/home/pragya/data/dashcam/nexar/hf` (outside the repo; `/data` was not writable by this user, so the home disk was used: 321 GB free at start) | 2,857 files, 31,379,033,414 bytes |
| DoTA annotations | `github.com/MoonBlvd/Detection-of-Traffic-Anomaly` @ `f8f603b8c06a946bc314752947ed480a4f33f82a` | `/home/pragya/data/dashcam/dota/repo` (+ `annotations_zip/`) | 24 MB |
| DoTA frames | Drive file `1RQp4hOP9X7TW6S3_vbqZvFSkrbbFzrRj`; Drive folder `1_WzhwZC2NIpzZIpX7YCvapq66rtBc67n` | **not downloaded**: 3 attempts on the full archive, then 1 on the split folder, all HTTP 404 (gdown and curl) | — |

**Download method:** `hf download --local-dir` with up to 5 retries, run in tmux, logged to `/home/pragya/data/dashcam/logs/`. The token was read from `hf-token.txt` into the process environment only, never printed or written.

**Completeness check:** a `DOWNLOAD_COMPLETE` marker is written only after `verify_nexar_download.py` confirms that every remote file exists locally at the remote size.

- *Implementation fix:* on the first run, a transient DNS failure made `hf download` exit 0 without downloading anything. The script then wrote a false marker. I removed the marker and added the size check before restarting.

**SHA-256 manifest:** `results/data_check/nexar_sha256_manifest.txt` covers every source file; there are no archives. DoTA metadata-file hashes are in `dota_metadata_check.json`.

## Nexar: expected vs observed

| check | expected | observed |
|---|---|---|
| rows, all splits | 2.84k | **2,844** (train 1,500; test-public 667; test-private 677) |
| train videos | 1,500 | **1,500** |
| train positive / negative | 750 / 750 | **750 / 750** |
| collision / near-collision | 400 / 350 | **not available**: no column distinguishes them (F1) |
| metadata rows vs files | — | 0 rows without a file, 0 files without a row, 0 duplicates, in every split |
| resolution | 1280×720 | **1280×720** for all 2,844 |
| codec | — | H.264, yuv420p, no audio stream (all 2,844) |
| fps | ~30 | avg_frame_rate 30.0 for 892/1,500 train videos; the rest spread 28.9–31.0 (30.6: 256, 29.9: 103, 30.5: 86, …) (F4) |
| train duration | ~40 s, bimodal | min 14.0, p5 18.0, p25 39.56, **p50 40.13**, p75 40.36, max 60.0 s. Bimodal: 163 at 18–20 s and 1,259 at 38–42 s; also 4 at 60 s and 2 at 14–16 s |
| test duration | ~10 s | test-public positive p50 9.97 (8.13–10.90); test-private positive p50 10.00 (8.57–11.00) |
| corrupt / unreadable | — | **0 / 2,844** (ffprobe and full `ffmpeg -f null` decode, both error-free) |

**Metadata columns** (identical in all six CSVs): `file_name, time_of_event, time_of_alert, light_conditions, weather, scene, time_to_accident`.

**Missingness:**
- `time_of_event` and `time_of_alert` are present for every positive in all three splits and absent for every negative.
- `time_to_accident` is empty for all of train and present for all test rows (0.5 / 1.0 / 1.5).
- `weather` is empty for 1 train positive and 1 train negative.

### Timing: train positives (n = 750, seconds)

| quantity | min | p5 | p25 | p50 | p75 | p95 | max | mean |
|---|---|---|---|---|---|---|---|---|
| time_of_event − time_of_alert (published: mean 1.6, max 4.5) | 0.033 | 0.400 | 0.986 | 1.433 | 2.089 | 3.283 | **4.466** | **1.600** |
| footage after event (duration − time_of_event) | 3.20 | 8.54 | 19.57 | 20.20 | 20.78 | 21.67 | 36.44 | 19.28 |
| footage before alert (= time_of_alert) | 1.966 | 8.53 | 17.29 | 18.26 | 18.98 | 20.07 | 55.47 | 17.50 |

- **≥ 1 s after event:** 750/750 (1.000). **≥ 2 s after event:** 750/750 (1.000).
- **≥ 3 s before alert:** 749/750 (0.9987). The one exception is `00383.mp4`: alert 1.966 s, event 3.032 s.
- **≥ 4 s before event:** 748/750 (0.9973).
- Alert never comes after the event, and never coincides with it (event − alert > 0 for all 750).

### Negatives

Negatives are stored as separate `negative/` folders with their own `metadata.csv`. They carry **no reference time**: `time_of_event` and `time_of_alert` are empty for all 1,422 negatives across splits. In the test splits, negatives do carry `time_to_accident` (0.5 / 1.0 / 1.5, e.g. test-public 142 / 116 / 75), even though there is no event to measure it against.

### Light, weather, scene (train; positive / negative)

- **light:** Normal 680 / 675, Twilight 41 / 47, Dark 22 / 25, Bright 7 / 3
- **weather:** Clear 445 / 474, Cloudy 243 / 252, Rain 60 / 23, Snow 1 / 0, empty 1 / 1
- **scene:** Urban 475 / 309, Highway 171 / 208, Sub-urban 75 / 196, Other 22 / 12, Rural 3 / 15, Industrial 3 / 10, Nature 1 / 0

The test splits are in `dashcam_data_check.json`; test-private negatives include 3 Fog.

## Findings

- **F1:** collision and near-collision are not distinguishable from the downloaded files. The 400/350 split comes from the paper; nothing on disk carries the type. Contact sheets therefore use the spec's fallback (10 positives + 5 negatives).
- **F2:** event − alert matches the published mean and max (1.600 vs 1.6; 4.466 vs 4.5).
- **F3 (test timebase; needs your read):** for test positives, if the timing fields referred to the ~10 s clip, `time_of_event − clip duration − time_to_accident` would be about 0. Observed:
  - test-public: median **9.08 s** (min −0.008, max 15.95)
  - test-private: median **9.13 s** (min −0.009, max 25.22)

  Only 18/672 are within 0.5 s of 0. So the test `time_of_event`/`time_of_alert` are in the full source video's timebase (about 20 s, like train), and the test clip is an excerpt that ends `time_to_accident` before the event. Its start offset isn't given in the metadata. The card doesn't say which timebase is used. **This does not affect train**: train clips are the full videos, and every train `time_of_event` falls inside its video. Test clips contain no post-event footage by design.
- **F4 (fps):** the frame rate is not a constant 30. `avg_frame_rate` ranges from 28.9 to 31.0, and only 892/1,500 train videos report exactly 30.0. Timestamps should be computed from decode times, not as frame index / 30.
- **F5 (duration outliers):** the duration distribution is bimodal (18–20 s and 38–42 s) as the card says, with 4 train videos at 60 s and a 14–16 s tail.

## Contact sheets (inspection only; not for selecting or excluding clips)

These are in `results/data_check/contact_sheets/`. All 15 are under 500 KB (largest 182 KB), and all 240 frames decoded.

**Sample:** seed 0, `random.Random(0).sample` over the file-name-sorted train positives (10), then train negatives (5).

**Layout:**
- **Row 1:** 8 frames evenly across the clip.
- **Row 2 (positives only):** 8 frames evenly across [event − 4 s, event + 2 s].
- **Labels:** each frame shows its timestamp `t=` and its offset from the event `ev±`. Frames at or after the alert are tagged `>=alert`, and the frame nearest the alert has an orange border.

**Per-frame record:** `results/data_check/nexar_contact_sheets.json`.

**Sheets:**
- **Positives:** `nexar_positive_01_00547`, `02_00594`, `03_00057`, `04_00364`, `05_00709`, `06_00675`, `07_00574`, `08_00428`, `09_00665`, `10_00505`
- **Negatives:** `nexar_negative_11_01922`, `12_01383`, `13_01798`, `14_01266`, `15_01478`

Implementation fixes, applied before the final sheets: the default font couldn't draw "Δ" or "≥", so those labels became `ev` and `>=`. Seeking to D − 1/fps returned no frame, so the last sample is now taken at the video-stream duration − 2/fps.

## DoTA: metadata only (frames unavailable)

| check | expected | observed |
|---|---|---|
| metadata_train / metadata_val | 3,275 / 1,402 | **3,275 / 1,402** (0 overlapping keys) |
| annotation JSONs | — | 4,677; 0 metadata keys without one; `num_frames` and `anomaly_start` agree with metadata for all |
| Σ num_frames | metadata 477,650; paper 731,932 | **477,650** (metadata and annotation JSONs alike). On-disk total: **not measurable**, so which figure the disk matches can't be determined |
| frames on disk, per-clip counts, missing clips, resolution, encoding, unreadable frames | — | **not measurable** (frames unavailable) |
| ego-5 clips (turning, lateral, moving_ahead_or_waiting, oncoming, start_stop_or_stationary) | 2,261 | **2,261** |
| ego-5 pre-onset (anomaly_start / 10 fps) | — | median 3.6 s, p5 1.5, p95 6.7 |
| ego-5 ≥ 2 / 3 / 4 / 5 s before onset | — | 0.896 / 0.680 / 0.403 / 0.197 |
| ego-5 ≥ 2 / 4 s after onset | — | 0.946 / 0.838 |

## Stop-and-ask conditions

- **Labels/timing meaning differently from the description:** for train, no. For test, F3 shows the timing fields are in the source-video timebase, which the card doesn't state. Reported for your decision; nothing was changed.
- **Nexar positives commonly lacking footage after the event, or under 3 s before the alert:** no. 750/750 have ≥ 2 s after; 749/750 have ≥ 3 s before.
- **> 1 % corrupt or missing:** Nexar 0 %. DoTA frames: 100 % missing (download blocked, reported).
- **Deleting data, changing source, filtering or changing a definition:** none done.

## Scripts (rerunnable, in `experiments/data_check/`)

- `download_nexar.sh` + `verify_nexar_download.py`
- `download_dota.sh` (blocked)
- `nexar_check.py`
- `nexar_contact_sheets.py`
- `dota_metadata_check.py`
- `dashcam_combine.py`

## GPU

Run on a separate host-level check at the end of the session (see final response). None of this job's processes used a GPU: ffprobe/ffmpeg on CPU, Python without CUDA.
