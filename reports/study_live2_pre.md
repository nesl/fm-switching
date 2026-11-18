# StudyLIVE2-pre: round-1 pre-pilot prerequisites 1 to 3

Status: COMPLETE 2026-11-17 22:10 to 22:16 (h100nvl; GPU 2 for Part 3), run unattended under the user's overnight
protocol. Pre-registered in research/EXPERIMENTS.md (StudyLIVE2-pre) before any work. HEAD at start 8e222f80
(`git pull --ff-only`: already up to date). Authority: the user's StudyLIVE2-pre prompt; research/policy_design_log.md
on this HEAD runs to D97 only (D98 to D105, cited by the prompt, are not in the repository yet), so the prompt's own
text is the specification used.

## Summary

| part | what | verdict |
|---|---|---|
| 1 | encode and store the round-1 JPEGs once (D91), manifests, E10a distributional check | **PASS** (full coverage; no quartile flagged); the two OVERNIGHT input-parsing decisions (section 2) were CONFIRMED by the user on 2026-11-18 |
| 2 | dense calibration refit (D86, D105) | **STOP, NOT RUN**: the live coordinator's monitoring body produces no score the calibration can use (section 3) |
| 3 | cache isolation on the real engine (D84) | **PASS** under the pre-registered rule (section 4) |

Consequence for the queue: the pilot's precondition P1 needs Part 2's FINAL calibration file, so the pilot cannot start
until the coordinator records a cloud score and Part 2 runs.

## 1. What was run

- Part 1 (CPU, no server): `~/.venvs/fm-switching-vllm/bin/python experiments/orchestration/study_live2_pre.py part1
  --procs 32` (22:12:28 to 22:12:53).
- Part 3 (GPU 2, request-harness pattern): `study_live2_pre.py part3` through `logs/live2_pre_chain.sh` (exports the GPU 2
  UUID and the HF token without printing it), server 22:14:24 to 22:15:56.
- Server (the round-1 configuration): StudyENG1c's KV-HOST launch command, i.e. the flags of ENG1c's DE_c38 server
  (the same flags StudyENG1e used), with ONLY `--kv-offloading-size 38 -> 27`; flag diff against DE_c38 recorded as
  `[('38', '27')]`. Full command in `results/orchestration/live2/pre/live2_pre_server.json`. vLLM 0.31.0 (engine line
  "v0.31.0"), Qwen3-VL-32B-Instruct @0cfaf481, prefix caching ON, GPU KV pool 62,944 tokens (checked), host offload
  mmap 28.99 GB = 27 GiB (checked), ENG1 stat-logger plugin loaded (observe-only, as in ENG1c), no ENG1e add-on.
  GPU 2 exclusive at start and end.

## 2. Part 1: encode and store

**Coverage (1a).** Source frames: Nexar StudyD14 / D14b SMALL PNGs, `~/data/dashcam/d14_frames/small` and
`~/data/dashcam/d14b_frames/small` (131,794 PNGs); S-EMBER raw frames `~/.cache/fm-switching/sember_frames` (234
sessions). Against the row sets:

| row set | rows | covered | missing |
|---|---|---|---|
| dense Orin set (StudyORIN1-dense, `orin1_dense_scores.jsonl.gz`) | 42,014 instants over 300 clips | 42,014 (every instant maps to the committed D14b N = 1 request's frame, which exists and whose sha256 matches) | 0 |
| the 300-clip set the dashcams play (`nexar_clip_meta`, D14b trace) | 300 | 300 (all in the dense set; no dense clip outside it) | 0 |
| S-EMBER EVAL sessions (`eval_sessions`, committed split) | 164 sessions | 164; 32,142 D2 frames at the 2-s stride, reaching every session's last question | 0 |

**OVERNIGHT DECISIONS (Part 1), CONFIRMED by the user on 2026-11-18 (decisions 1 and 2 accepted).** `experiments/orchestration/live2/data/
encode_jpeg.py` was written on flash without the data, and its two input parsers do not match the stores on this host:

1. Nexar frames are stored as `<clip>/<pts_ms>.png` (StudyD14 / D14b `d14b_prepare.py`), not `<clip>_t<seconds>.png`;
   run unchanged, the script would have stored every frame as UNPARSED. Decision: the frame for instant (clip, t) is
   taken from the committed D14b N = 1 request manifest (`results/dashcam/study_d14b/d14b_requests_manifest.jsonl.gz`,
   `frame_keys[0]`, the latest frame with pts <= t, sha256 verified on all 42,014), and encoded with the script's
   recipe (`Image.open(png).convert("RGB").save(JPEG, quality=90)`).
2. S-EMBER D2 is not an r1_inputs construction (`~/.cache/fm-switching/r1_inputs` holds only RICH and RECENT npz). E10a
   built D2 from `sember_frames` with `study_rh3_inputs.load(path, (352, 256))` (`experiments/cost/study_e10a_sizes.py`
   lines 84-85). Decision: D2 frames at the 2-s stride (`t % 2 == 0`, the RH4 / RH6 selection) of every EVAL session,
   loaded with that loader and saved with `save(JPEG, quality=88)`.

Reason: both preserve the data and the pre-registered design (same source frames, same encoder call, same quality,
same frame references as `fleet/trace.py`), and neither substitutes a different source; the prompt's "do not
substitute" concerns missing frames, and none are missing. Flash's scripts were not edited; `build_manifest.py` ran
UNCHANGED on the store layout it expects.

**Encode and check (1b).** Pillow 12.3.0, libjpeg(-turbo) 6.2 (recorded in each manifest).

| store | frames | sizes | bytes p25 / median / p75 / mean | E10a p25 / median / p75 / mean | ratios | flagged |
|---|---|---|---|---|---|---|
| `~/data/live2/jpeg/nexar_q90` | 42,014 | 768x432 (all) | 47,844 / 62,472 / 75,486 / 62,670 | 49,810 / 63,898 / 75,682 / 63,319 | 0.961 / 0.978 / 0.997 / 0.990 | no |
| `~/data/live2/jpeg/sember_d2_q88` | 32,142 | 256x352 (30,610), 352x256 (1,532) | 19,870 / 24,200 / 28,940 / 24,642 | D2 256x352: 21,483 / 25,597 / 30,614 / 25,760 | 0.925 / 0.945 / 0.945 / 0.957 | no |

(The S-EMBER store is also compared with E10a's D2 352x256 quartiles in its manifest_meta, also unflagged.) Every
stored frame has its sha256 and byte count in the manifest; source frames were only read.

**Commit-ready outputs (1c).** `results/orchestration/live2/pre/manifests/` (manifest rows gzipped, manifest_meta and
encode_meta per store). The JPEGs stay in `~/data/live2/jpeg/` and are not committed.

## 3. Part 2: dense calibration refit, STOPPED

The prompt requires extracting the 32B's score "with the SAME function the live coordinator uses on cloud answers" and
says to STOP if the coordinator records a different score from the one the calibration needs. On this HEAD:

- the live monitoring request (`experiments/orchestration/live2/coordinator.py` around line 368, `_submit(kind=
  "monitor", ..., question=None, ..., max_tokens=4)`, body from `bodies.build_body`) carries the header
  `"D2 history"` and one frame, NO question and NO `logprobs`;
- nothing sets `cloud_score`: the fleet emulator writes `cloud_score=None` (`fleet/emulator.py:136`) and no other
  module assigns it;
- the calibration is on `log p_yes` (`live2/calib.py`: `sigmoid(a * log p_yes + b)`), and the scorer refuses AP when a
  cloud answer carries no score (`scorer/score.py` lines 385-389).

So there is no coordinator score to extract and no body that elicits a Yes / No log-probability; Part 2 is NOT RUN and
nothing was written under `results/orchestration/live2/calibration/`. This is the STOP condition "score extraction
mismatch"; under the overnight protocol it is recorded and the queue continues. It is expected to be resolved by
StudyLIVE2-fix on flash (the pilot's precondition P2); Part 2 is re-run on the same server configuration once the
coordinator records a cloud score.

## 4. Part 3: cache isolation (D84)

The six-step procedure of `reports/study_live2_coord.md` section 3, with the live2 code: `cachekeys.run_tag(0,
"live2_pre_isolation")`, `cachekeys.cache_salt(tag, device)` per device, mm uuids `"<run_tag>|<device_id>|<session_id>|
<frame_ref>"` from `cachekeys.mm_uuid`, bodies from `bodies.build_body` (header `coordinator.HEADER_TEXT`, max_tokens 1,
streamed), usage parsed with `backend.cached_tokens_of`. Nexar: clip 00005.mp4, its first 16 dense instants (stored
q90 JPEGs) in one request. S-EMBER: session 1011205677616862_start_0.0_end_314.103, history H0 = D2 frames before 60 s
(30 frames), append = the next 30 s (15 frames), delta mode (uuid-only references for frames the device already sent,
bytes for new ones).

| step | device | request | prompt tokens | cached tokens | required |
|---|---|---|---|---|---|
| 2 | A | Nexar clip, first send | 5,419 | 0 | (expected 0) |
| 3 | B | same clip, B's first send | 5,419 | **0** | == 0 |
| 4 | A | A's repeat, unchanged | 5,419 | **5,408** | > 0 |
| 5a | A | S-EMBER H0, first send | 2,711 | 0 | (expected 0) |
| 5b | A | 30 s append: references for H0 + bytes for new | 4,061 | 2,704 (A's own prefix) | (expected > 0) |
| 5c | B | the same content, B's first send | 4,061 | **0** | == 0 |
| 5d | A | A's repeat of its append, unchanged | 4,061 | **4,048** | > 0 |

**Verdict: PASS** (pre-registered rule: B's first send of content A already sent reports 0 in steps 3 and 5, AND A's
repeat reports > 0 in steps 4 and 5). Every request returned HTTP 200 and carried its device's `cache_salt` and mm
uuids. Server version: vLLM 0.31.0, command as in section 1.

## 5. Consistency checks (applicable parts)

1. Cross-check: JPEG bytes against E10a's committed quartiles, ratios 0.925 to 0.997 (section 2), none over 10 %;
   prompt tokens of a 16-frame Nexar request 5,419 = 16 x 338.7, consistent with StudyD14b's 378-token single-frame
   request (header and question included there); D2 history 2,711 tokens for 30 frames = about 90 per image, StudyRH4's
   D2 accounting (`d2_batch_tokens`: 90 per image + 31 header).
2. Physical plausibility: not a latency study; the cached counts are block-aligned (5,408 = 338 blocks of 16; 4,048 =
   253 blocks), as prefix caching requires.
3. Distribution sanity: byte distributions reported with quartiles; per-frame values in the manifests.
4. Definition audit: frame refs as `fleet/trace.py` puts them on the wire; D2 = 352x256 (or 256x352 by orientation),
   2-s stride, q88 (E10a, RH4); Nexar = 768x432 SMALL, q90 (E10a Job A, D70).
5. Claim linkage: D84 (devices never share cache entries) is verified on the real engine; D91 (encode once, single
   source) is satisfied for both datasets; D86 / D105 (dense calibration) is NOT satisfied (Part 2 stopped).
6. Proxy validity: none used.

## 6. Open issues

- Part 2 blocked on the coordinator: a monitoring body that elicits a scored Yes / No answer (question plus
  `logprobs`) and a function that turns the answer into `log p_yes` and stores it as `cloud_payload.cloud_score`.
- The two Part 1 input-parsing decisions (section 2) were confirmed by the user on 2026-11-18; flash's `encode_jpeg.py`
  parsers should still be aligned with the stores so the next encode needs no wrapper.
- The pilot's precondition P2 (StudyLIVE2-fix on origin, design log rows D98 to D105) does not hold on this HEAD.

## 7. Files

New: `experiments/orchestration/study_live2_pre.py`, `reports/study_live2_pre.md`, `results/orchestration/live2/pre/`
(`manifests/{nexar_q90,sember_d2_q88}_{manifest.jsonl.gz,manifest_meta.json,encode_meta.json}`,
`live2_pre_coverage.json`, `live2_pre_part1.json`, `live2_pre_server.json`, `live2_pre_cache_isolation.json`,
`live2_pre_monitor_h100nvl.jsonl`, `live2_pre_statlog.jsonl`, `live2_pre.log`).
Changed: `research/EXPERIMENTS.md` (pre-registration row, verdict in place), `results/INDEX.md`, `research/STATUS.md`.
Not committed: the JPEG stores under `~/data/live2/jpeg/`.

## 8. Part 2 re-run (2026-11-18): dense calibration, FINAL

User ruling 2026-11-18: run Part 2 now with the committed StudyD3 scored body that StudyLIVE2-fix2 copies into the live
coordinator, then confirm the live body once fix2 is on origin.

**2a Server.** The same round-1 configuration as Part 3 (vLLM 0.31.0, 32B @0cfaf481, GPU 2, prefix caching ON, GPU
pool 62,944, host offload 27 GiB; flag diff vs ENG1c DE_c38 `[('38', '27')]`), started 07:39, stopped 08:33.

**2b Requests.** For each of the 42,014 dense instants: `experiments/dashcam/d3_infer_vllm.py` `body()` (header "The
following is 1 dashcam frame.", the committed QUERY of lines 43-44, GEN = temperature 0.0, max_tokens 8, seed 0,
logprobs True, top_logprobs 20) with ONE change, `stream=True`, the instant's stored q90 JPEG from Part 1, and a
per-request `cache_salt` (sha256 of "live2pre-p2|frame_ref|attempt", so no request can reuse another's cache entries).
Concurrency 8. Score = `d3_infer_vllm.yes_no()` on the first generated token's top-20 log-probabilities, then
log(p_yes) (as `ctrl1c_calibrate.py` lines 276-277 and 298). Result: 42,014 of 42,014 HTTP 200, 0 retries needed,
0 unscored (every first token was Yes or No: 41,096 "No", 918 "Yes"); median TTFT 0.553 s; 32B raw score median
-15.63 (p10 -21.75, p90 -5.26). Per-request rows: `results/orchestration/live2/pre/live2_pre_part2_requests.jsonl.gz`.

**Body check (after fix2 landed on origin, HEAD 5f6d01f + this study's commits).** Five instants (00005.mp4 t3.00,
00463.mp4 t14.25, 00846.mp4 t16.25, 01348.mp4 t35.25, 02137.mp4 t39.25) were rebuilt with the live coordinator's
`bodies.build_body(kind="monitor")`: after removing the D84 cache keys (`cache_salt`, the per-image `uuid`) and the
stream fields, the two bodies are BYTE-IDENTICAL (equal sha256 of the sort_keys serialization) for all five, and the
image data URLs are identical as well. The only asymmetry is `stream_options`, which the live body adds; fix2 declares
`stream` and `stream_options` as one transport exemption, and it is counted under the user's "stream" exemption here
(it changes usage reporting only, not generation). Fix2's extraction runs StudyD3's own `yes_no` (by AST), the function
used here. **Check PASSED; the calibration file is relabelled FINAL** (`live2_pre_part2_bodycheck.json`).

**2c Labels.** The per-instant labels of the scorer's streaming AP (`scorer/score.py` AP_HORIZONS 0.0 / 0.5 / 1.0 /
1.5 s; StudyE9b `target_index` on its absolute 0.25-s grid from t = 3.0): a positive clip's instant is positive iff it
is that clip's AP target for some horizon (600 instants: 4 per positive clip, all on the 0.5-s dense cadence); every
instant of a negative clip is negative (20,467). The other 20,947 instants of positive clips have NO label under that
definition and are not in the primary fit (rule: the AP never scores them). A secondary fit with the clip-level label
on every instant (the StudyCTRL1c / ORIN2 convention, 42,014 instants) is reported for the comparisons below.

**2d Fit.** Platt maps (`ctrl1c_calibrate.fit_platt`, unregularised IRLS) for both tiers (32B on the new JPEG scores,
Orin on the committed StudyORIN1-dense scores), 5-fold cross-fitted BY CLIP with the committed StudyCTRL1c fold map
(within each label stratum, order by sha256(file_name), fold = rank mod 5; 60 clips per fold). Output
`results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json`: label FINAL, fit_sample dense, the
clip-to-fold map, per-fold (a, b) and n for each tier and label set, the request-body template hash, the JPEG manifest
hash, the server record and the body check.

**2e Results.**

| labels | tier | per-fold a (folds 0..4) | a mean [min, max] | b mean | OOF log loss | base-rate log loss | n |
|---|---|---|---|---|---|---|---|
| primary (AP) | 32B | 0.136, 0.129, 0.142, 0.155, 0.128 | 0.1381 [0.1280, 0.1548] | -1.674 | 0.1193 | 0.1294 | 21,067 |
| primary (AP) | Orin | 0.147, 0.110, 0.143, 0.147, 0.116 | 0.1326 [0.1103, 0.1474] | -2.209 | 0.1240 | 0.1294 | 21,067 |
| secondary (clip) | 32B | 0.082, 0.079, 0.079, 0.077, 0.075 | 0.0785 [0.0751, 0.0819] | 1.206 | 0.6671 | 0.6928 | 42,014 |
| secondary (clip) | Orin | 0.084, 0.054, 0.077, 0.063, 0.054 | 0.0665 [0.0536, 0.0844] | 0.781 | 0.6845 | 0.6928 | 42,014 |

Out-of-fold reliability (primary): 32B, bins [0, 0.1) n = 20,121 predicted 0.024 observed 0.024, [0.1, 0.2) n = 946
predicted 0.132 observed 0.118; Orin [0, 0.1) n = 20,646 predicted 0.028 observed 0.028, [0.1, 0.2) n = 421 predicted
0.108 observed 0.040 (the Orin's upper bin is over-confident). Secondary reliability per decile is in the file.

Comparison of slope a (32B / Orin):

| map | 32B a | Orin a | ratio this / that (32B, Orin) |
|---|---|---|---|
| this run, primary (AP labels) | 0.1381 | 0.1326 | |
| INTERIM (32B pre-JPEG D3-DEV; Orin ORIN2) | 0.1295 | 0.1149 | 1.07, 1.15 |
| CTRL1c 16.2 dense D14b-DEV-90 (clip labels) | 0.0500 | 0.0381 | **2.76, 3.48** |
| this run, secondary (clip labels) vs D14b-DEV | 0.0785 | 0.0665 | 1.57, 1.74 |

The two differences over 2x (primary vs D14b-DEV) are a label-definition effect, not a disagreement in the scores: the
AP labels make only near-event instants positive (the AP targets lie 0 to 1.5 s before the event), which sharpens the
map exactly as CTRL1c section 16.2 found for its event-anchored D3 sample (2.6 to 3.0x steeper than D14b-DEV); with the
clip-level label on the same instants the dense fit is within 1.8x of D14b-DEV. Tier offset (raw log p_yes at p = 0.5,
32B minus Orin, as in CTRL1c 16.2): primary -4.54 (both crossings are extrapolated above 0 because the AP base rate is
2.8 %), secondary -3.61; CTRL1c: -4.32 (D3) and -3.86 (D14b-DEV). The out-of-fold calibrated Orin minus calibrated 32B
offset is therefore about 4 raw log units under every definition, so the D57 per-tier calibration remains necessary.

Consistency: the JPEG scores are on the same definition as StudyD14b's committed `score` (log p_yes); fold map, fit
function and label engine are the committed ones; no result marked INVALID was used.

Schema note (2026-11-18, after the FINAL relabel, no number changed): the calibration file also carries the keys the
live scorer's loader reads (`live2/fleet/data_sources.calibration()`): top-level `a` / `b` (pooled Orin map), 
`compare.h100_32b` (pooled 32B map), and `folds = {n_folds 5, by clip, assignment, maps[k]}` where `maps[k]` restates
the primary fit with fold k held out. The pooled maps are fitted on all 21,067 labelled instants (Orin a 0.1320,
b -2.214; 32B a 0.1377, b -1.678); the scorer never uses them for a clip the fold assignment places, so every clip is
scored out of fold. The loader reads the file as FINAL with 5 folds over 300 clips.

## 9. Part 1 extension (2026-11-18): S-EMBER D2 store to the END of every EVAL session

User request. The committed 1 fps source frames (`~/.cache/fm-switching/sember_frames`, written by
`experiments/sember/study_o_q4.py::cache_video`) stop one frame after each session's last question (`max_qt` + 1 s), so
Part 1's D2 store ended there too. `experiments/orchestration/study_live2_pre_ext.py` runs THE COMMITTED `cache_video`
(executed unchanged from the file by AST: PyAV decode at 1 fps, PIL JPEG q88) with `max_qt` = the session's duration,
from the cached session videos (`~/.cache/fm-switching/sember_videos`), into a NEW directory
(`~/.cache/fm-switching/sember_frames_full/`); the existing source frames were not modified. Check: every one of the
64,208 frames the new extraction shares with the existing directory is BYTE-IDENTICAL (sha256), in all 164 sessions.
Then the same D2 recipe as Part 1 (`study_rh3_inputs.load(path, (352, 256))`, JPEG q88) encoded ONLY the 2-s-stride
instants the store did not hold: **6,437 new D2 frames, store now 38,579 frames** (existing JPEGs untouched, D91), and
the UNCHANGED `build_manifest.py` rebuilt the manifest with the E10a check: **no quartile flagged** (vs D2 256x352:
p25 / median / p75 / mean ratios 0.921 / 0.941 / 0.940 / 0.951; vs D2 352x256: 0.992 / 0.980 / 0.977 / 0.996). Every
session now reaches its last decodable frame (16 sessions end 1.00 to 1.03 s before their fractional end, e.g. last frame
599.0 s for an end of 600.011 s, because the 1 fps decoder has no frame past it). Outputs:
`results/orchestration/live2/pre/manifests/sember_d2_q88_{manifest.jsonl.gz, manifest_meta.json, encode_meta.json}`
(replaced), `results/orchestration/live2/pre/live2_pre_part1_extension.json` (per-session record). The pilot's
combined manifest and frame-ref symlinks under `~/data/live2/` were refreshed to include the new frames.

## 10. D111 (2026-11-18): end-of-session frames, and a correction to section 9

**Correction to section 9.** Section 9 says every session now reaches its last decodable frame. That is true, but it is
not the same as covering every instant a trace can ask for. The boundary convention is: **trace end INCLUSIVE, frame
store EXCLUSIVE.** The trace generator's 2-s history grid includes t = 2 x floor(duration / 2) <= duration, while the
1 fps store ends at its last decodable frame, up to about 1 s before the end (for example a 300.000 s session's last
1 fps frame is 299.0 s, and its grid asks for 300.0 s). StudyMOT2 seed 9's preflight (`live2/preflight.py`) found the
first such reference and refused to start, which is what the preflight exists for.

**Enumeration (D111 step 1).** `experiments/orchestration/study_live2_d111_endframes.py enumerate` built every trace a
planned run uses, with the runner's exact `generate_trace` call and the combined manifest, and ran the preflight's
every-ref check on each: MOT2 seeds 9 and 10 (12 devices, 600 s); the pilot at seed 0 (the 8-device 120 s Step 1 trace
and every ladder size 4, 8, ..., 512 at 600 s); round 1 at seeds 1, 2, 3, every size 4 to 128, all three ratios (600 s,
mode A; mode B's records are the same, only the digest's view differs). 1,136 traces. **25 distinct references were
missing**, every one an S-EMBER D2 end-of-session instant (24 sessions at 300.0 / 322 / 326 / 336 / 422 / 600 s ends,
listed with the traces using each in `results/orchestration/live2/pre/d111_enumeration_before.json`), used by 970 of
the 1,136 traces (MOT2: seed 9 only, 1 ref; pilot ladder: 6 traces; round 1: 963); the largest share of any single
trace's references was 0.053 % (STOP threshold 1 %). One more session (1200.004 s) has the same gap but no planned trace
reaches its end. The generation was checked against a real run: MOT2 seed 10's regenerated trace has the same four
hashes as the trace that run used.

**Substitutes (D111 step 2).** All 25 by the PREFERRED method (a): the source video's last native-rate frame at or
before the requested instant, decoded from the same `~/.cache/fm-switching/sember_videos/<session>.mp4` the D2
extraction used, through the extractor's own steps (`frame.to_image()` saved as JPEG q88) and the same D2 recipe
(`study_rh3_inputs.load(path, (352, 256))`, JPEG q88). The videos are 12 fps, so every substitute's capture time is
0.0833 s before its requested instant (offset 0.083333 s in all 25; within the 0.1 s rule); no fallback (b) was
needed. Each is marked in the encode log and, through a three-field additive change to `build_manifest.py` that only
substitute rows exercise, in the manifest: `substitute_of` (`<session>.mp4@pts<capture time>`), `method`
(`native_last_frame`), `offset_s`, and `sha256`. No existing JPEG was touched (D91); store now 38,604 frames.

**Checks (D111 step 3).**

| check | result |
|---|---|
| preflight every-ref check on all 1,136 traces after the fill | 0 missing, all pass |
| traces unchanged (trace_sha256, device_answers_sha256, fairness_digest_A, fairness_digest_B) | 0 of 1,136 changed (robot history bytes come from the committed default, not the manifest) |
| E10a byte quartiles, whole store, committed 10 % rule | unflagged (256x352: 0.921 / 0.941 / 0.940 / 0.951; 352x256: 0.992 / 0.980 / 0.977 / 0.996) |
| E10a byte quartiles, the 25 NEW frames only, committed 10 % rule | **FLAGGED on small samples**: 256x352 (n = 15) p25 0.736, median 1.031, p75 1.078, mean 1.009; 352x256 (n = 10) p25 0.884, median 1.113, p75 1.017, mean 1.006. Means within 1 %; quartiles of 10 to 15 frames are noisy |
| each substitute vs its own session's previous stored frame (bytes ratio) | median 1.002, range 0.591 to 1.136 (two near 0.6, candidate: end-of-recording scene change or fade, not tested) |

The small-sample quartile flag is reported, not acted on: D111's STOP conditions (a ref unfillable, more than 1 % of
a run's refs substituted, any trace or digest change) were not met, and the substitutes are the true last frames of
their videos by the committed recipe. Outputs: `results/orchestration/live2/pre/manifests/sember_d2_q88_{manifest.jsonl.gz,
manifest_meta.json, encode_meta.json, encode_log.jsonl.gz}`, `results/orchestration/live2/pre/d111_{enumeration_before,
enumeration_after, fill, verify}.json`. The combined manifest and frame-ref symlinks under `~/data/live2/` were
refreshed (25 new links).
