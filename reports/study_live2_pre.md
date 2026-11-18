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
