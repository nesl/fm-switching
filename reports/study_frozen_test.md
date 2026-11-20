# StudyFROZEN-test (H100, overnight 2026-11-19 to 20): frozen-policy test, StudySS1-32B and SS timing

**Status: IN PROGRESS. Last updated 2026-11-19 19:45.** Rules: D116 (no methodological change overnight; never seeds 1
to 3 or HOLDOUT; never INVALID results; GPU 2 exclusive; no em dashes). PROVISIONAL decisions are marked.

## HEADLINE AFTER D144 (2026-11-20 07:45)

D144 (user, 2026-11-20): sizes 16 and 18 (20 saturated: b7 n20 s0 delivered 2 of 28 robots); a dropped or
over-context request is a per-question MISS, the run counts (error count and requests offered recorded, saturated if
> 5 percent errored); seed 0 is back for every arm. Where a cell had a first attempt and a rule-5 rerun, the FIRST
attempt is the cell (PROVISIONAL); reruns kept and labelled. The scorer (41b0eae) already counts an undelivered
request as a miss with the device answer standing; only b7 n16 s0's first attempt needed rescoring (17 of 24, equal to
its rerun). Robot counts reconcile with the scorer in every run (`frozen_feasible.json`, all_match_scorer true).

**Common support, 16 devices, seeds 0, 4, 5 (seed 6 hybrids running):**

| arm | robots on time over FEASIBLE (of 55) | over all (of 69) | SS on time at 2 s (of 1,069) | request errors (s0, s4, s5) |
|---|---|---|---|---|
| b7 | 50 | 50 | 969 | 1, 0, 0 |
| eco-llm | 49 | 50 | 890 | 1, 0, 0 |
| mooncake | 50 | 50 | 970 | 0, 0, 0 |
| **hybrid-F-lhreq** | **53** | **54** | **1,023** | 1, 0, 0 |
| hybrid-F6-lhreq | 51 | 52 | 1,011 | 1, 0, 0 |

Dashcams all meet in every cell. Seed 6 (baselines only so far): b7 14 of 14 feasible / 337 SS, eco-llm 13 of 14 /
301, mooncake 14 of 14 / 334. No run is saturated by the 5 percent rule.

**CAPACITY VERDICT, CORRECTED (user, 2026-11-20).** The earlier statement "no run meets capacity" was WRONG for D133:
it came from the scorer's `capacity_met`, which computes the robot target over ALL questions (`robot_pool_on_time /
robot_pool_n`, e.g. hybrid-F s4 15 of 20 = 0.75). Under D133 the robot target is p 0.90 within 5 s over FEASIBLE
questions (matched per opportunity_id, flash's feasibility rule); the all-questions figure is reported beside it and
does not decide capacity. Verdict per run = dashcams all meet AND robot feasible on-time >= 0.90 AND >= 20 pooled
robot questions (the D82 count of all robot questions in the run) AND SS on time >= 0.90 within 2 s. Every row below
states both denominators; the scorer's own flag (all-questions rule) was false in every row.

| run | dashcams | robot feasible | robot all (pool) | SS at 2 s | D133 verdict |
|---|---|---|---|---|---|
| b7 n16 s0 | meet | 17 of 18 (0.944) | 17 of 24 | 317 of 356 (0.890) | fails (SS) |
| b7 n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 332 of 357 (0.930) | **MEETS** |
| b7 n16 s5 | meet | 19 of 22 (0.864) | 19 of 25 | 320 of 356 (0.899) | fails (robot, SS) |
| b7 n16 s6 | meet | 14 of 14 (1.000) | 14 of 20 | 337 of 357 (0.944) | **MEETS** |
| eco-llm n16 s0 | meet | 16 of 18 (0.889) | 17 of 24 | 292 of 356 (0.820) | fails |
| eco-llm n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 294 of 357 (0.824) | fails (SS) |
| eco-llm n16 s5 | meet | 19 of 22 (0.864) | 19 of 25 | 304 of 356 (0.854) | fails |
| eco-llm n16 s6 | meet | 13 of 14 (0.929) | 13 of 20 | 301 of 357 (0.843) | fails (SS) |
| mooncake n16 s0 | meet | 17 of 18 (0.944) | 17 of 24 | 319 of 356 (0.896) | fails (SS) |
| mooncake n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 332 of 357 (0.930) | **MEETS** |
| mooncake n16 s5 | meet | 19 of 22 (0.864) | 19 of 25 | 319 of 356 (0.896) | fails (robot, SS) |
| mooncake n16 s6 | meet | 14 of 14 (1.000) | 14 of 20 | 334 of 357 (0.936) | **MEETS** |
| hybrid-F n16 s0 | meet | 17 of 18 (0.944) | 18 of 24 | 341 of 356 (0.958) | **MEETS** |
| hybrid-F n16 s4 | meet | 15 of 15 (1.000) | 15 of 20 | 339 of 357 (0.950) | **MEETS** |
| hybrid-F n16 s5 | meet | 21 of 22 (0.955) | 21 of 25 | 343 of 356 (0.963) | **MEETS** |
| hybrid-F6 n16 s0 | meet | 16 of 18 (0.889) | 17 of 24 | 335 of 356 (0.941) | fails (robot) |
| hybrid-F6 n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 334 of 357 (0.936) | **MEETS** |
| hybrid-F6 n16 s5 | meet | 21 of 22 (0.955) | 21 of 25 | 342 of 356 (0.961) | **MEETS** |
| eco-llm n14 s0 | meet | 11 of 11 | 12 of 15 | 315 of 357 | not measurable (pool 15 < 20) |
| mooncake n14 s0 | meet | 11 of 11 | 11 of 15 | 326 of 357 | not measurable (pool 15 < 20) |
| b7 n20 s0 | FAIL | 2 of 19 | 2 of 28 | 5 of 477 | fails (saturated size) |

At 16 devices, seeds 0, 4, 5: hybrid-F meets D133 in 3 of 3 runs, hybrid-F6 2 of 3, b7 and mooncake 1 of 3 (2 of 4
with seed 6), eco-llm 0. The binding constraint for the baselines is single-shot on time (b7 s0 misses at 0.890 by
four questions); for hybrid-F6 at s0 it is the robot feasible fraction (16 of 18). Several verdicts sit within one or
two questions of the 0.90 line.

## MORNING SUMMARY (2026-11-20 07:25)

**What ran overnight.** StudySS1-32B and StudySS2-32B (complete, numbers only, on origin); the SS timing measurement;
the D134 published-baseline queue (19:52 to 21:05, on MIXED, while waiting); then the THREE-TYPE frozen grid from
21:08 (1200 s, 40:40:20, LH-REQ EVAL robots, SS RefSpatial + RealWorldQA EVAL, tight 27 GiB, push-all, memory
enforcement on), baselines first and hybrid-F-lhreq / hybrid-F6-lhreq from 02:16 after "policy-F ready (frozen)".
The grid is still running (14-device cells now; 20 and 24 deferred, see decision 6).

**Headline table, 16 devices, common support (seeds 4 and 5 complete for every arm; all runs valid, 0 request errors,
dashcams all meet in every run, no run meets capacity). All-questions robot figure; feasible-question column to be
added offline (needs the trace-side feasibility rule, run when no driver is active).**

| arm | robots on time, s4 + s5 | SS on time at 2 s, s4 + s5 | robot answers sent as RECENT | seed 6 (robots / SS) |
|---|---|---|---|---|
| b7 | 33 of 45 | 652 of 713 | 0 of 36 | 14 of 20 / 337 of 357 |
| eco-llm | 33 of 45 | 598 of 713 | 8 of 44 | 13 of 20 / 302 of 357 |
| mooncake | 33 of 45 | 651 of 713 | 0 of 36 | 14 of 20 / 335 of 357 |
| **hybrid-F-lhreq** | **36 of 45** | **682 of 713** | 8 of 44 | queued (06:32 refusal) |
| hybrid-F6-lhreq | 35 of 45 | 676 of 713 | 9 of 44 | queued (06:32 refusal) |

Reading: on two seeds hybrid-F is ahead of every baseline by 3 robot questions of 45 and 30 SS questions of 713;
F6 does not improve on F. Two seeds and small margins: a direction, not a settled effect. mooncake equals b7 on
every seed: its 377 keep-warm actions find nothing resident (memory enforcement evicted nothing in any run; peak
GPU-resident history 0), an unexercised mechanism, not evidence about mooncake.

**hybrid-F6 caveat (decision period).** C6 is alive live (375 and 385 chooser calls, 13 and 12 decisions changed,
c6_scorer_error 0) but it breaches the 100 ms decision period: 322 and 323 of about 12,000 periods over 100 ms
(2.7 percent), p99 207 and 150 ms, max 670 and 517 ms; hybrid-F's p99 is 1.3 ms with 0 breaches. An F6 result is
therefore partly a late coordinator, reported beside it, not discarded.

**Skipped cells (INVALID twice, rule 5; data kept):** eco-llm, hybrid-F and hybrid-F6 at 16 devices seed 0 and
eco-llm at 14 devices seed 0 (one seed-0 LH-REQ question whose history reaches 33,839 tokens, over the 32,768
context; seed 0 only, every size); b7 at 20 devices seed 0 (127 and 111 transport ReadErrors: overload, 97 percent of
the committed 32B peak). Headline uses common support (seeds 4, 5, 6) so no arm is selected by its representation
choice; seed-0 b7 and mooncake are kept and marked excluded-from-headline.

**Incidents (not measurements, all set aside):** 21:05 every cell refused at preflight (single-shot images not
staged; fixed); 02:12 eleven cells refused (my own dry proof overlapped a boundary; repaired); 06:32 three cells
refused (an automatic git gc triggered by the driver's commits, up to 819 percent CPU; repo-local gc.auto disabled,
cells requeued).

**Decisions still needed from the user:** (1) grid sizes 16 and 20 (20 overloads the server) or 16 and 18; (2) do
transport errors invalidate a run or count as misses; (3) does an over-context request invalidate a run or count as
a miss (a miss restores seed 0 for every arm); (4) C6 does about 94 percent of its work on single-shot requests,
against D143 C's robot-only design; guarding it would change decisions.

## 0. Morning summary (kept current)

- **StudySS1-32B: DONE and on origin** (numbers only, no qualification verdict). VizWiz val 4,319 of 4,319 scored, mean
  VQA accuracy 0.665; EgoThink 700 of 700 scored, mean containment 0.477; 0 errors; manifest order verified; prefix
  cache verified cold (0 hits; positive control passed). flash runs the EgoThink judge and the device comparison.
- **SS timing: DONE.** 32B TTFT for one single-shot VizWiz request: idle p50 0.41 s / p90 0.67 s; 12-device b7
  background p50 0.66 s / p90 2.59 s; 16-device b7 background saturates the engine (TTFT 9.9 to 43 s on the 24
  requests served in the run window). Robots in both backgrounds were MIXED ("lh-req ready" was not on origin).
- **StudySS2-32B: DONE and on origin** (numbers only). RefSpatial-Bench 277 of 277, mean point-in-mask accuracy 0.371;
  RealWorldQA 765 of 765, exact match 0.712; 0 errors; manifest order verified; prefix cache 0 hits. CODA-LM was not
  in the kit (licence).
- **Policy grid: NOT STARTED.** It needs "lh-req ready" on origin (robots are LH-REQ only; nothing runs on MIXED for
  the grid). hybrid-F and hybrid-F6 need "policy-F ready". Neither commit was on origin at 18:55.

## 1. StudySS1-32B (D142 item 3)

Kit at 8492e02 (`experiments/casestudy/ss1_*`, files unchanged), run through `experiments/casestudy/ss1_cloud_run.py`,
which only manages the server. Outputs `results/casestudy/study_ss1/vizwiz_val_cloud32b.json` (92430ba) and
`egothink_cloud32b.json` (743a8b1).

| dataset | n | scored | errors | score (kit scorer) | TTFT p50 | run order |
|---|---|---|---|---|---|---|
| VizWiz val | 4,319 | 4,319 | 0 | mean VQA accuracy 0.665 | 0.31 s | manifest order, verified 4,319 of 4,319 |
| EgoThink | 700 | 700 | 0 | mean containment 0.477 (judge by flash) | | manifest order, verified 700 of 700 |

**Condition:** H100 NVL, vLLM 0.31.0+cu129, the live2 round-1 32B server (Qwen3-VL-32B-Instruct @ 0cfaf481, served as
32BI) started fresh for the run, idle, one request at a time, greedy (temperature 0, seed 0); image processor overridden
by the round-1 `--mm-processor-kwargs` (min area 4,096 px; the released default, used by the Orin, is 65,536).

**Implementation fix (reported):** vLLM 0.31.0 rejects a `cache_salt` containing '/', and the kit passes the question id
as the salt; the first attempt failed every request (HTTP 400) and wrote nothing. The wrapper's shim replaces '/' with
'_' in the salt only (it never reaches the model).

**Cache verification:**
- Prefix cache: 6.70M prompt tokens queried, 0 hits, on one server instance used only by the run (no probe reached it).
  **Positive control PASSED** on a fresh start with the same command
  (`results/orchestration/live2/ss_timing/prefix_cache_positive_control.json`): a unique-salt repeat of the same
  request read 0 cached tokens (3 of 3), a same-salt repeat read 1,232 to 1,248 of 1,238 to 1,250. The control's own
  first reader coerced an absent field to 0 (a vacuous-pass defect); it was fixed before the control ran (a peer review
  by the A6000 session) and the near-miss is recorded in the control's file.
- Multimodal encoder cache: keyed by image CONTENT, not by salt. Byte-identical photos under different file names: 34
  groups in VizWiz (36 repeat questions), 15 in EgoThink (16). Hits: VizWiz 36 of 36 candidates, EgoThink 16 of 16, at
  exactly the predicted positions (a census, no eviction). Lists: `vizwiz_shared_images.json`,
  `egothink_shared_images.json` (TTFT-only artifacts; accuracy unaffected).
- **Resolution difference against the device:** 28 VizWiz images are below the released 65,536-px minimum area (the
  smallest 23x30); the device upscales them and the H100 server does not, so those questions saw different pixels
  (accuracy AND TTFT; `vizwiz_below_min_pixels.json`). EgoThink has none. Full image sizes:
  `ss1_image_dims.jsonl`.

## 1b. StudySS2-32B

Kit at 1b8790c (`experiments/casestudy/ss2_*`, files unchanged), run through `experiments/casestudy/ss2_cloud_run.py`
exactly as StudySS1-32B (fresh round-1 server, idle, one request at a time, greedy, unique cache_salt with the same '/'
shim, the kit's own `_provenance` with device h100nvl). Data from the public sources (BAAI/RefSpatial-Bench,
xai-org/RealworldQA), decoded with the builder's own loops without rewriting the manifests; all 1,042 images match the
manifests' hashes and every question, object and reference matches. CODA-LM is skipped by the kit (images need a
non-commercial agreement).

| dataset | n | scored | errors | score (kit scorer) | run order | commit |
|---|---|---|---|---|---|---|
| RefSpatial-Bench | 277 | 277 | 0 | mean point-in-mask 0.371 (location 0.513, placement 0.286, unseen 0.299); 9 answers with no parsed point | manifest order, verified | 6f7abc4 |
| RealWorldQA | 765 | 765 | 0 | exact match 0.712 (MCQ 0.715 of 438; free-form 0.709 of 327) | manifest order, verified | cb79d82 |

**Cache:** prefix cache 0 hits on both (86,082 and 1,001,747 queried tokens, per-dataset deltas). Multimodal cache:
RefSpatial asks several questions per image (277 questions on 91 distinct images); **186 hits against 186 predicted
repeats** once the candidates are keyed on DECODED PIXELS. Keyed on the parquet's source bytes the prediction was 180:
6 images differ in bytes but not in pixels, and the content-keyed cache treats them as one. RealWorldQA 3 of 3.
Candidate lists `results/casestudy/study_ss2/*_shared_images.json` (TTFT-only; accuracy unaffected).

## 2. SS timing (D142 item 4)

`experiments/orchestration/live2/ss_timing.py`, driver `experiments/orchestration/study_ss_timing_driver.sh`. The same
100 VizWiz val questions (seed 0 sample, excluding the 70 on shared images) through the kit's body, one at a time,
unique salt each. Background: the live2 harness, b7, dashcam : robot 50:50, push-all, seed 0, 600 s, tight 27 GiB;
robots **MIXED** (labelled; "lh-req ready" was not on origin). The injector starts after the background run is
deciding and sends one request every 5 s from about t = 60 s.

| condition | served | TTFT p50 | p90 | max | background run |
|---|---|---|---|---|---|
| idle | 100 of 100 | 0.41 s | 0.67 s | 0.79 s | none |
| 12 devices, b7, MIXED | 100 of 100 | 0.66 s | 2.59 s | 5.39 s | valid, dashcams all meet |
| 16 devices, b7, MIXED | 24 of 100 | 22.5 s | 37.1 s | 43.3 s | valid, **dashcams fail, robots 2 of 35** |

At 16 devices b7 push-all saturates the engine: the injected requests' TTFT climbs from 9.9 s (t = 83 s) to 43 s, so
the one-at-a-time injector fell behind its 5-s schedule, served 24 within the run, and the other 76 failed after the
background server stopped (75 refused, 1 cut mid-stream). The 16-device figure therefore describes a saturated
engine, sampled 24 times, not a 100-request distribution. For the SS deadline (2 s proposed): idle and 12-device p50
are within it; the 12-device p90 (2.59 s) is not.

## 3. Policy grid (overnight plan items 2 to 4)

- **Workload:** THREE-TYPE (40 : 40 : 20, SS deadline 2 s) if the user rules by 21:00, else TWO-TYPE (50 : 50, labelled
  "two-type (no SS ruling by 21:00)"). Tight 27 GiB, push-all, memory enforcement on, 600 s.
- **Memory enforcement:** new runner flag `--kv-capacity-enforced` (sets `CoordState.kv_capacity_enforced`, recorded
  in the run header). Step 2b proof: section 4.
- **Arms:** b7, eco-llm, mooncake; hybrid-F and hybrid-F6 when "policy-F ready" lands (proofs checked on origin first).
  Sizes 12 and 16, seeds 0 and 4; then seeds 5 and 6; then 10 and 20, seeds 0 and 4.
- **Gate:** robots LH-REQ only. As of 18:55 neither "lh-req ready" nor "policy-F ready" is on origin, so no grid cell has
  run and GPU 2 is idle by rule.

## 4. Memory enforcement, Step 2b

**Dry proof: UNEXERCISED, not passed** (`results/orchestration/live2/frozen_test/kv_enforcement_step2b.json`). Decision
logs with `--kv-capacity-enforced` off vs on, 600-s dry runs on MIXED traces (LH-REQ not ready), b7, eco-llm and
mooncake at 12 and 16 devices: **0 differing decisions in all six pairs, and peak GPU-resident history 0 tokens in
every run**. The dry harness never builds GPU-resident history, so enforcement cannot fire there; this is an
unexercised link (CLAUDE.md Rule 2), not evidence that enforcement does nothing.

**Live instrumentation added (output only):** the runner now writes `memory_pressure` into
`coordinator_result.json`: the enforcement flag, `gpu_kv_tokens`, CoordState's pressure record (epochs, epochs over
cap, peak tokens, over-cap intervals) and the totals of `enact_placement`'s per-call counts (offloaded, kept warm,
**evicted**, resident), which cstate computes and previously discarded. Every grid cell therefore reports whether
enforcement evicted anything. The harness tests pass, including "a split run decides exactly as an in-process run"
(13 tests). Note from live residency logs: under b7 every robot history is believed cold to the end of a run, so for
b7 enforcement may have nothing to evict; the per-cell eviction count will show it.

## 4b. Overnight rules (user, 2026-11-19) and decisions taken

Rules: run length from flash's committed table (shortest of 600 / 900 / 1200 s with >= 20 pooled robot questions in
all 8 cells, 12 and 16 devices, seeds 0, 4, 5, 6, 40:40:20, EVAL-only LH-REQ robots), same for every arm, committed
before the grid; DEV-fitted tables on EVAL-only questions; if "policy-F ready" is not on origin by 01:30, b7, eco-llm
and mooncake start the three-type grid and hybrid-F / hybrid-F6 join at the next run boundary after it lands; a
component that does not move decisions is an ABSENT LINK and the freeze proceeds (only base-with-switches-off != b7
stops F and F6); INVALID = rerun once then skip and log; server crash = one restart then next cell; push conflict =
rebase unpushed only.

Decisions (PROVISIONAL unless ruled):
1. 19:52, by the user's instruction ("run some baselines, pick up bumped work"): the D134 published-baseline queue
   resumed on MIXED while waiting (ruled; later confirmed as a standing rule).
2. The D134 driver's placement watcher would have paused on flash's `a0f4159` (credit-axis hardening and pressure
   instrumentation); marked handled because it needs no H100 wiring (placement path applied since e924005).
   PROVISIONAL.
3. The grid will not run a substitute workload under the THREE-TYPE label: if, when it is due, the harness cannot yet
   express LH-REQ EVAL robots or the RefSpatial + RealWorldQA EVAL single-shot pool, or the run-length table is not
   committed, the D134 queue keeps GPU 2 busy and this is recorded here. PROVISIONAL.
4. As of 20:20: "policy-F built (not frozen)" (a3e3dd0) is on origin, not "policy-F ready"; the trace generator
   accepts the 40:40:20 ratio but its single-shot pool is still StudySS1's (VizWiz, EgoThink) and has no LH-REQ robot
   selection; no run-length table yet.

## 4c. The three-type grid as run (updated 2026-11-20 01:30)

**Setup:** `experiments/orchestration/study_frozen_grid_driver_v3.sh`; 1200 s (flash's committed run-length table);
40:40:20 dashcam : LH-REQ EVAL robot : single-shot (RefSpatial + RealWorldQA, EVAL part of the committed 30/70 split);
SS deadline 2 s, one per 10 s per assistive device; tight 27 GiB; push-all; `--kv-capacity-enforced`; runner flags
`--robot-question-set lh_req --ss-question-set ss2` (both cross-checked against flash's committed counts: n=16 seed 0
gives 24 robot and 356 SS questions). Started 21:08 on "ss2-pool ready" (user ruling), so the 01:30 rule-3 fallback
was already satisfied. Scored with flash's three-type scorer (41b0eae); pre-fix three-type numbers are never compared.

**Valid runs so far (all questions; feasible-question column to follow):**

| arm | n | seed | dashcams all meet | robots on time | SS on time (2 s) | capacity | mm gate (hits = same-ID repeats; SS repeats) |
|---|---|---|---|---|---|---|---|
| b7 | 16 | 0 | yes | 17 of 24 | 319 of 356 | no | 405 = 405; 0 |
| mooncake | 16 | 0 | yes | 17 of 24 | 319 of 356 | no | 405 = 405; 0 |
| b7 | 16 | 4 | yes | 14 of 20 | 332 of 357 | no | 285 = 285; 0 |
| eco-llm | 16 | 4 | yes | 14 of 20 | 294 of 357 | no | 345 = 345; 0 |
| mooncake | 16 | 4 | yes | 14 of 20 | 332 of 357 | no | 285 = 285; 0 |
| b7 | 16 | 5 | yes | 19 of 25 | 320 of 356 | no | 735 = 735; 0 |

**Skipped (INVALID twice, rule 5; data kept):** eco-llm n16 s0 (one request of 33,839 tokens exceeds the 32,768
context, deterministically: one LH-REQ session at seed 0 whose history reaches 33,781 tokens at t = 958 s; absent at
seed 4); b7 n20 s0 (127 and 111 transport ReadErrors).

**PROVISIONAL decisions taken (all overnight):**
5. Multimodal-cache gate redefined: the planned "total hits 0" cannot hold, because D84 deliberately lets robot recall
   resend a session's history frames under the same per-(device, frame) UUID. Pass condition used: mm_cache_hits delta
   equals the run's repeated-UUID references, AND 0 repeats among single-shot references; wire presence of the uuid
   key counted per image part (asyncbackend). Every valid run so far passes exactly (agreed with the A6000 session).
6. Sizes 20 and 24 deferred to the end of the queue (driver v3, `DEFER_SIZES`), no cell dropped: at 20 devices the
   offered dashcam load is 14.67 req/s, 97 percent of the committed 32B peak (StudyD7b, 15.10 req/s); b7 n20 s0 failed
   twice with transport ReadErrors starting at t = 510 s, the StudyMOT1 / StudyD7 overload signature (server log
   silent; client dispatch lag p90 1.2 to 1.3 s against 28 ms at 16 devices). eco-llm n20 s0 was stopped 4 minutes in
   and set aside. Pending the user's size ruling (the A6000 recommends 16 and 18: 73 and 85 percent of peak).
7. The 1,042 StudySS2 images were staged in the live frame store as the kit's own JPEG q90 bytes (they were absent, so
   the first launch at 21:05 was refused at preflight for every cell: not measurements, set aside).
8. hybrid-F / hybrid-F6 join only after "policy-F ready" and a check that base-with-switches-off is byte-identical to
   b7; every F6 cell must show c6_calls > 0 and c6_scorer_error == 0 or it is INVALID as not-F6 (the A6000 found a
   swallowed MissingEvidence that silently disabled C6 before its fix).

**Mechanism notes:** memory enforcement never evicted anything in any run (peak GPU-resident history 0): b7 and
eco-llm hold no resident history, and mooncake's 377 keep-warm state actions (n16 s4) find nothing resident, so its
outcomes match b7 on both seeds. Unexercised, not evidence. Single-shot accuracy is device-side only: cloud-served
SS answers are recorded but not scored in live2 (the StudySS2 scorers are not importable there).

**Pending user rulings:** grid sizes (16 and 20, or 16 and 18); whether transport errors invalidate a run or count as
misses; whether an over-context request invalidates a run or counts as a miss.

## 5. Incidents

- 17:10 to 17:16: the first StudySS1-32B attempt failed every request (cache_salt '/'), stopped, no answers written.
- Host Python while the StudySS1 server was measuring idle TTFT: a py_compile and short edit or read scripts (seconds
  each), recorded here; no measured request overlapped a heavy process.

## 6. A6000 morning summary, policy-F side (2026-11-20 07:30)

Written by the A6000 session, which owns the policy-F freeze and the dry proofs. The MORNING SUMMARY section,
section 0 and sections 4c and 5 remain the H100's; nothing above this line was edited. Everything here is DRY (the
live2 trace generator with `--dry`, no engine), so every number is a decision-log count, never a served request. The
live grid is the H100's.

### 6.1 What ran

Committed in `8f8e36c` "policy-F ready (frozen)", pushed from a worktree at origin/main and verified ANCESTOR and
EQUAL before the worktree was removed. Controls before the push: the fleet suite 234 of 234 through its own runner,
`test_hybrid.py` 7 of 7 through pytest, and 0 em dashes in everything added.

Four proofs, all on a three-type LH-REQ cell unless stated. Full output in
`results/orchestration/live2/hybrid/policy_f_proofs.json`; the narrative is `reports/study_policy_f.md` section 11.

**Proof 1, ruling B is inert on robots.** `hybrid-F` is byte-identical to the screened `hybrid2-c1c2k15c3c5` on all
four two-type cells: 6,554 / 8,087 / 6,472 / 7,872 decisions, matching digests, `ss_seen` 0 in each.

**Proof 2, Step 2b per component.** Each switch toggled alone against the full arm. Two metrics are reported because
they are different registers and the first one misled me:

| component | decisions moved (setwise) | log positions differing | verdict |
|---|---|---|---|
| C1 | 0 | 0 | **ABSENT LINK**, cancelled by geometry |
| C2 | 712 | 12,071 | moves decisions |
| C3 | 459 | 6,026 | moves decisions |
| C5 | 461 | 11,986 | moves decisions |
| C6 | 3 | 11,794 | moves decisions |

`_differing` counts log POSITIONS and is kept only for the identity proofs, where byte-identity including order is
the claim. One early divergence desynchronises the rest of the log, so C6 read 11,794 positional against 3 actual, a
3,931x gap, and C2 17x. `_differing_setwise` counts a multiset over `(t, kind, opportunity_ids, representation,
defer_s)` and is the right register for "did this switch move a decision". The register error was caught by the
negative control, not by inspection.

C1's zero is **cancelled by geometry**, not unexercised: dashcam items carry one constant `value` and one constant
`work`, so `idx` is monotone in slack which is monotone in deadline, making C1's dashcam order identically EDF order;
and `_cap_dashcam_only` keeps every recall item unconditionally (`hybrid_arm.py:436-437`), so C1 reaches only the
`order` channel, which the harness discards. That is two of the five null categories at once and neither is evidence
about the policy.

**Proof 3, dry smoke, 30 of 30 cells ran** (5 arms x {16, 20, 32} x seeds {0, 4}, decision counts):

| n | seed | F | F6 | b7 | eco-llm | mooncake |
|---|---|---|---|---|---|---|
| 16 | 0 | 13,564 | 13,582 | 13,623 | 13,621 | 14,001 |
| 16 | 4 | 13,525 | 13,525 | 13,570 | 13,570 | 13,947 |
| 20 | 0 | 16,361 | 16,362 | 16,382 | 16,343 | 16,885 |
| 20 | 4 | 16,504 | 16,542 | 16,512 | 16,475 | 17,010 |
| 32 | 0 | 15,863 | 16,123 | 16,150 | 16,353 | 16,910 |
| 32 | 4 | 15,977 | 15,983 | 16,236 | 16,436 | 16,985 |

F differs from F6 at five of the six (n, seed) pairs and is identical at n=16 seed 4 only, so the F6 arm is live
everywhere else. Per PROVISIONAL decision 8 in section 4c, a live F6 cell must also show `c6_calls > 0` and
`c6_scorer_error == 0`.

**Proof 4, value-term negative control, 0 decisions moved on all eight cells.** Four patch variants (a flat table
with every value equal, dashcam 100x, robot 100x, single-shot 1,000x) against both frozen arms. Setwise 0 everywhere;
the only non-zero positional cell, robot_100x at 2 of 16,361, is two `release_recall` rows swapping places at
t = 527.0 with both items released either way.

### 6.2 The three findings

**1. The value term is decision-inert in both frozen arms.** A flat table and a 10,000x inversion move nothing. So
D143 ruling A's LH-REQ swap, the 4.4x half-one correction and the SS ordering flip (refspatial 0.18742 over robot
0.13204) all change a quantity the frozen policy does not read. **The SS ordering must not be read as evidence about
single-shot work versus robot recall**; it is a quantity with no reader.

**2. C6 was dead in every `-lhreq` cell and I caused it.** `_LhReqFittedProfiles._DEV_KEY` mapped 4 of the 5
`(representation, tier)` conditions the escalation path reads, raising `MissingEvidence` on `cloud RICH` (4 of 12
question types map to RICH) and on `device N1`. `_c6_prepare`'s bare `except Exception` counted that into
`c6_scorer_error` and returned False, so `c6_live` was False on every period while `live2_describe` still reported
`c6=True`. Measured before the fix: `c6_scorer_error` 251 of 251 periods with recall, `c6_calls` 0, F6 byte-identical
to F at all six smoke cells. After re-raising `MissingEvidence` and declaring the two substitutions: `c6_calls` 254,
`c6_dev_send_to_hold` 6, `c6_scorer_error` 0. A swallowed exception counted into a counter is the same shape as the
write-only field: every surface sign said the arm was configured.

**3. C6 spends 94 percent of its work on requests D143 ruling C says it cannot act on, and breaches the decision
period at every size.** Call split by request type:

| n | SS-only periods | calls on SS | mixed or robot periods | calls on robot | deviations |
|---|---|---|---|---|---|
| 16 | 356 | 356 | 24 | 24 | 1 on robot |
| 20 | 476 | 478 | 28 | 28 | **1 on single-shot** (`c6_dev_send_to_hold`) |

Per-period `decide()` wall time against the 100 ms decision period:

| arm | n | all p50 | all p99 | SS-only p50 / p99 | robot p50 / p99 |
|---|---|---|---|---|---|
| F | 16 | 0.029 | 0.046 | 0.039 / 0.057 | 0.039 / 0.079 |
| F6 | 16 | 0.030 | 63.848 | 42.638 / 211.968 | 74.957 / 285.178 |
| F | 20 | 0.033 | 0.048 | 0.043 / 0.080 | 0.043 / 0.054 |
| F6 | 20 | 0.034 | 124.524 | 81.747 / 268.761 | 117.976 / 873.407 |
| F | 32 | 0.044 | 0.069 | 0.054 / 0.158 | 0.054 / 0.184 |
| F6 | 32 | 0.045 | 249.680 | 133.494 / 345.450 | 146.144 / 403.470 |

So the breach recorded at 32 devices exists at **every** size including the n=16 entry point, 2x to 9x over the
period at p99. Gating C6 to non-SS recall would cut roughly 42 s of C6 time per 1200 s cell to 3.3 s, a 92 percent
cut, but **it would delete the one SS decision at n=20**, so the speed fix is NOT decision-preserving under D108 and
D121 and I have not applied it. D143 ruling C's "C6 is robot-only by design" is false as implemented.

### 6.3 The over-context question, and why a per-arm skip is unsafe

LH-REQ session `1848337166005249` reaches 33,781 history tokens, which with the prompt is the H100's 33,839 against
the 32,768 context. Checked with the committed trace generator at all four development seeds:

| seed | max session tokens | worst question history | questions over 32,768 |
|---|---|---|---|
| 0 | 44,581 | 33,781 | 1, at n=16, 18 and 20 alike |
| 4 | 27,031 | 24,331 | 0 |
| 5 | 27,031 | 24,331 | 0 |
| 6 | 27,031 | 24,331 | 0 |

It is a seed-0 phenomenon only, the same session at every size, and seeds 4, 5 and 6 have 8,437 tokens of headroom
at their worst question. The p90 session history is about 1,800 tokens, so this is one session at 19x the p90.

**The selection effect.** The arms that hit the request (F, F6, eco-llm) are the ones that chose to send full
history; b7 and mooncake survive seed 0 because they did not. Skipping the cell per arm leaves a seed-0 panel
containing only the arms whose representation choice avoided the overflow, which is the thing the study measures.
Recommended instead: **common support**, seeds 4, 5 and 6 for every arm in the headline, with the seed-0 b7 and
mooncake cells kept as recorded and marked excluded-from-headline rather than deleted. Cost, which is the argument
for ruling the question a per-question miss instead: pooled robot questions at n=16 are 24 / 20 / 25 / 20 across
seeds 0, 4, 5, 6, so common support gives **65 against 89**, a 27 percent loss of the robot denominator on a study
already at the D82 minimum of 20 per cell.

### 6.4 Grid size, offered load against the committed peak

Offered dashcam load is a step function of the dashcam device count, against the committed 32B one-frame closed-loop
peak of 15.10 req/s (StudyD7b):

| n | dashcam devices | offered req/s | percent of peak |
|---|---|---|---|
| 14, 16 | 6 | 11.01 | 73 |
| 17, 18 | 7 | 12.83 | 85 |
| 19, 20 | 8 | 14.67 | 97 |
| 32 | 13 | 23.83 | 158 |

The ReadErrors at 20 devices match the StudyMOT1 and StudyD7 overload signature exactly (no HTTP status, no server
log line, client dispatch lag p90 1.2 to 1.3 s against 28 ms at 16 devices). StudyMOT1's own amended rule selected
66 percent of peak. The A6000 recommends **16 and 18**, and 18 holds the same pooled robot counts as 16
(24 / 20 / 25 / 20), so the second size costs no denominator.

### 6.5 PROVISIONAL decisions taken on this side (overnight rule)

1. **Two substitutions in the LH-REQ DEV fit**, because the escalation path reads five `(representation, tier)`
   conditions and the LH-REQ DEV split measures three. `("RICH", "cloud") -> cloud_D2` (D2 is the fullest measured
   cloud condition and RICH is at least as informative, so this credits the cloud with less) and
   `("N1", "device") -> device_4B_RECENT` (N1 is the device without history coverage, so its true accuracy is at most
   the covered device's, and using the covered number credits the device with more). Both understate the cross-tier
   gain, so neither can manufacture an escalation advantage. Declared in `_SUBSTITUTED` and asserted by
   `test_lh_req_dev_fit_covers_every_condition_the_policy_reads`.
2. **C1's value term left as the two-type constant** rather than moved to the DEV fit (0.13204 against 0.142857).
   Inert either way per proof 4, so this is a hygiene question, not a results question.
3. **The SS 30/70 split is stratified** by question source.
4. **SS on-time is deliberately NOT a third capacity conjunct**, because D64 defines capacity as dashcam-all-meet AND
   robot-pool-meets. Folding it in would be a post-freeze definition change under D79.
5. **Two metrics shipped for decision diffs**, positional for identity claims and setwise for move claims, rather
   than replacing the first. Both appear in every proof row so a reader cannot pick up the wrong register silently.

### 6.6 Open user rulings, in the order work is blocked on them

1. **The over-context counting rule** for session `1848337166005249`: miss, or run-invalidating. Now blocking the
   headline's seed panel and worth 27 percent of the robot denominator.
2. **C6: byte-identity or the speed fix.** The two cannot both hold. Keeping byte-identity keeps a 2x to 9x breach
   of the decision period at every size; taking the fix deletes one SS decision and requires a relabel under D79;
   making C6 robot-only is what D143 ruling C already states and is the A6000's recommendation.
3. **Grid size**, 16 and 20 as ruled, against 16 and 18.
4. **Whether an inert value term is acceptable in a frozen policy**, given that three separate corrections to it
   changed no decision.
