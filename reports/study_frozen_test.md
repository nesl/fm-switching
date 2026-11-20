# StudyFROZEN-test (H100, overnight 2026-11-19 to 20): frozen-policy test, StudySS1-32B and SS timing

**Status: IN PROGRESS. Last updated 2026-11-19 19:45.** Rules: D116 (no methodological change overnight; never seeds 1
to 3 or HOLDOUT; never INVALID results; GPU 2 exclusive; no em dashes). PROVISIONAL decisions are marked.

## HEADLINE (user form, 2026-11-20 08:05): pooled rates with paired-by-seed bootstrap CIs

16 devices, common support seeds 0, 4, 5 (every arm; seed 6 added when hybrid-F6's seed-6 run lands). Rates pooled over
the seeds; on time = delivered within the deadline (robot 5 s, SS 2 s) by an HTTP 200 request. 95 percent CIs from a
bootstrap PAIRED BY SEED: opportunities resampled within each seed, the same draw for every arm (all arms share each
seed's trace), B = 10,000; differences against b7 on the same draws. Measurability (D82): every run has >= 20 robot
questions (24, 20, 25); feasible counts 18, 15, 22. File: `results/orchestration/live2/frozen_test/frozen_headline_n16.json`
(script `experiments/orchestration/live2/frozen_headline.py`).

| arm | robot on time over FEASIBLE | minus b7 | SS on time at 2 s | minus b7 | dashcam all-meet |
|---|---|---|---|---|---|
| b7 | 50 of 55 = 0.909 [0.836, 0.982] | | 969 of 1,069 = 0.907 [0.889, 0.923] | | 3 of 3 runs |
| eco-llm | 49 of 55 = 0.891 [0.800, 0.964] | [-0.055, 0.000] | 890 of 1,069 = 0.833 [0.810, 0.855] | **[-0.090, -0.058]** | 3 of 3 |
| mooncake | 50 of 55 = 0.909 [0.836, 0.982] | [0.000, 0.000] | 970 of 1,069 = 0.907 [0.890, 0.924] | [-0.004, +0.006] | 3 of 3 |
| hybrid-F-lhreq | 53 of 55 = 0.964 [0.909, 1.000] | [-0.018, +0.127] | 1,023 of 1,069 = 0.957 [0.944, 0.968] | **[+0.034, +0.067]** | 3 of 3 |
| hybrid-F6-lhreq | 51 of 55 = 0.927 [0.855, 0.982] | [-0.055, +0.091] | 1,011 of 1,069 = 0.946 [0.932, 0.959] | **[+0.022, +0.057]** | 3 of 3 |

Reading: on SS on time, hybrid-F and hybrid-F6 are ahead of b7 and eco-llm behind it, with CIs excluding zero; mooncake
equals b7. On robot on time over feasible questions no arm differs from b7 with a CI excluding zero (55 feasible
questions). Capacity is not reported until 18 devices is run (user ruling). Per-run D133 verdicts are in the table below,
labelled: **per-run verdicts are fragile: 14-15 feasible questions per run tolerate at most one miss at 0.90.**

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
| eco-llm | 49 | 49 | 890 | 1, 0, 0 |
| mooncake | 50 | 50 | 970 | 0, 0, 0 |
| **hybrid-F-lhreq** | **53** | **53** | **1,023** | 1, 0, 0 |
| hybrid-F6-lhreq | 51 | 51 | 1,011 | 1, 0, 0 |

**Correction (2026-11-20 08:05, found by the A6000 session, re-derived here from the run files).** A request the server
REFUSED was still counted on time: `coordinator.py` stamps a cloud answer's `on_time` from its completion time alone,
and the scorer's `_within` reads `t_delivered`, so the HTTP 400 over-context request (opp0010837, history 33,781
tokens) scored as an on-time cloud answer with letter "X" in eco-llm, hybrid-F and hybrid-F6 at 16 devices seed 0.
Rule applied from here on (D144): **on time = delivered within the deadline by a request that returned HTTP 200.**
Effect: the all-questions figure drops by one in exactly those three cells (eco-llm 17 to 16, hybrid-F 18 to 17,
hybrid-F6 17 to 16 of 24); every other n16 cell has 0 such answers. The question is INFEASIBLE by the trace rule, so the
feasible column and every D133 verdict are unchanged. The harness is not changed mid-sweep; the rule is applied in
analysis to every cell.

**RECENT charged but not sent: precise description (2026-11-20 08:40; user ruling: fix before the first RECENT-using arm).**
- CHARGED: `coordinator._submit_recall` computes `tokens = cstate.tokens_for_representation(rep)`; for RECENT that is the
  recent window, `RECENT_WINDOW_TOKENS` = 467 (capped at the history). The GPU budget is charged
  `recall_gpu_s(tokens, readiness)` and the submission carries `est_tokens = tokens`.
- SENT: the body's frame list is built from `s.frames`, EVERY frame of the session (375 frames on the over-context
  question), whatever the representation. The server therefore prefills the full history.
- SCORED: what was sent. The delivery time is the full-history prefill's, the cloud letter is answered from the full
  history; nothing in scoring sees the 467-token charge. So a RECENT release behaved exactly like a D2 release on the wire
  while being priced as RECENT.
- TOUCHED (completed runs; RECENT releases per run): eco-llm n16 s0 5, s4 5, s5 3, s6 5, n14 s0 3; hybrid-F n16 s0 5, s4 5,
  s5 3, s6 5; hybrid-F6 n16 s0 7, s4 6, s5 4, s6 7 (reruns the same). b7 and mooncake never release RECENT (372 of 372 D2).
  These RECENT releases are mostly infeasible robot questions that b7 would reject and C3 / eco-llm convert; sent as true
  RECENT they would likely arrive on time with lower accuracy. They cannot be RESCORED (the true RECENT request was never
  made); they need REDOING if the user wants these arms measured with RECENT actually sent.
- FIX (prepared, applied with the driver stopped before simplestream, harness tests run with no server up): a RECENT
  release sends the session's most recent k frames, k = ceil(frames x charged tokens / history tokens), at least 1;
  every other representation's frame list is byte-identical. Scheduling arms before simplestream run unchanged.


Dashcams all meet in every cell. Seed 6 (baselines only so far): b7 14 of 14 feasible / 337 SS, eco-llm 13 of 14 /
301, mooncake 14 of 14 / 334. No run is saturated by the 5 percent rule.

**PER-RUN D133 VERDICTS (fragile: 14-15 feasible questions per run tolerate at most one miss at 0.90; capacity itself is reported only once 18 devices is run).** Corrected 2026-11-20: The earlier statement "no run meets capacity" was WRONG for D133:
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
| eco-llm n16 s0 | meet | 16 of 18 (0.889) | 16 of 24 | 292 of 356 (0.820) | fails |
| eco-llm n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 294 of 357 (0.824) | fails (SS) |
| eco-llm n16 s5 | meet | 19 of 22 (0.864) | 19 of 25 | 304 of 356 (0.854) | fails |
| eco-llm n16 s6 | meet | 13 of 14 (0.929) | 13 of 20 | 301 of 357 (0.843) | fails (SS) |
| mooncake n16 s0 | meet | 17 of 18 (0.944) | 17 of 24 | 319 of 356 (0.896) | fails (SS) |
| mooncake n16 s4 | meet | 14 of 15 (0.933) | 14 of 20 | 332 of 357 (0.930) | **MEETS** |
| mooncake n16 s5 | meet | 19 of 22 (0.864) | 19 of 25 | 319 of 356 (0.896) | fails (robot, SS) |
| mooncake n16 s6 | meet | 14 of 14 (1.000) | 14 of 20 | 334 of 357 (0.936) | **MEETS** |
| hybrid-F n16 s0 | meet | 17 of 18 (0.944) | 17 of 24 | 341 of 356 (0.958) | **MEETS** |
| hybrid-F n16 s4 | meet | 15 of 15 (1.000) | 15 of 20 | 339 of 357 (0.950) | **MEETS** |
| hybrid-F n16 s5 | meet | 21 of 22 (0.955) | 21 of 25 | 343 of 356 (0.963) | **MEETS** |
| hybrid-F6 n16 s0 | meet | 16 of 18 (0.889) | 16 of 24 | 335 of 356 (0.941) | fails (robot) |
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

## 12. Offline analysis of the overnight grid (A6000, 2026-11-20, user request)

CPU only, no new runs. Every number comes from the committed run directories under
`results/orchestration/live2/frozen_test/runs`; the script is
`experiments/orchestration/live2/offline_grid_analysis.py` and its output is
`results/orchestration/live2/frozen_test/offline_grid_analysis.json`.

REGISTERS, because the five answers mix them. MEASURED means read from a run's own logs. MODELLED
means computed with the committed cost curve (`costs.recall_ttft_s` at COLD) on measured inputs.
CONSTRUCTED means a counterfactual bound: what a different policy could have had, never what
happened. Each table says which it is.

One scope note. The seed-6 cells of hybrid-F and hybrid-F6 landed while this analysis was being
written, and both ARE included: every arm's pooled row now covers seeds 4, 5 and 6 at 16 devices,
65 robot questions each, so the per-arm columns are like for like on the seed set. They are not
like for like on what happened to the questions: b7 and mooncake reject far more robot questions
than the hybrids, so their "missed" rows are dominated by questions that never reached the cloud at
all, which is a different event from a question that was sent and was late. Section 12.3 numbers
are at seeds 4 and 5 only, because that is the pairing that existed when they were computed. And b7 and mooncake reject
far more robot questions than the hybrids, so their "missed" rows are dominated by questions that
never reached the cloud at all, which is a different event from a question that was sent and was
late.

### 12.1 Robot miss decomposition (item 1), 16 devices, seeds 4 to 6, seconds, p50

| arm | outcome | n | never sent | wait before release | engine queue (residual) | prefill (modelled) | after first token | arrival to first token |
|---|---|---|---|---|---|---|---|---|
| b7-edf-feasibility | on time | 47 | 0 | 0.1222 | 0.6166 | 2.1211 | 0.0222 | 3.0249 |
| b7-edf-feasibility | missed | 18 | 14 | 0.1027 | 2.1847 | 3.9287 | 0.0222 | 6.1382 |
| eco-llm | on time | 46 | 0 | 0.1169 | 0.7103 | 2.1211 | 0.0222 | 2.9238 |
| eco-llm | missed | 19 | 1 | 0.1218 | 1.0691 | 5.3568 | 0.0222 | 6.6661 |
| hybrid-F-lhreq | on time | 50 | 0 | 0.0984 | 0.5662 | 2.1211 | 0.0222 | 2.9429 |
| hybrid-F-lhreq | missed | 15 | 1 | 0.1073 | 0.5675 | 5.3621 | 0.0222 | 6.0820 |
| hybrid-F6-lhreq | on time | 49 | 0 | 0.2840 | 0.4798 | 2.1211 | 0.0222 | 3.2306 |
| hybrid-F6-lhreq | missed | 16 | 1 | 0.4620 | 0.6380 | 5.3621 | 0.0222 | 6.5444 |
| mooncake | on time | 47 | 0 | 0.1097 | 0.7655 | 2.1211 | 0.0222 | 3.1148 |
| mooncake | missed | 18 | 14 | 0.1131 | 2.1408 | 3.9287 | 0.0222 | 6.1632 |

How the split is formed. Waiting before release is `t_submit - t_opportunity`, MEASURED. Prefill is
MODELLED: the committed COLD curve on the measured uncached prompt, and the uncached prompt is the
whole prompt in every robot request in every cell (see 12.2). The engine queue is the RESIDUAL,
`(t_first_token - t_submit) - prefill`, clamped at zero, so it carries the model's error; the JSON
records how often the model exceeded the measured TTFT per cell. "After first token" is
`t_delivered - t_first_token`, MEASURED, and is a constant by construction (12.3).

The shape: waiting before release is 0.10 to 0.52 s and never the binding term. Prefill of the
history is, at 2.12 s on the questions that met the deadline and 3.93 to 6.42 s on those that
missed. The 5 s robot deadline is spent on rebuilding the history, not on scheduling it.

### 12.2 Is "peak GPU-resident history 0" an observation (item 2)

Three independent instruments, 16 devices, seeds 4 to 6:

| cell | robot requests | with cached_tokens > 0 | residency rows | believed tiers | prefix_cache_hits | prefix_cache_queries | mm_cache_hits | telemetry_cached_tokens non-null |
|---|---|---|---|---|---|---|---|---|
| b7 s4 | 15 | 0 | 372 | all cold | 0 | 5,458,622 | 285 | 0 |
| b7 s5 | 21 | 0 | 370 | all cold | 0 | 5,548,713 | 735 | 0 |
| b7 s6 | 15 | 0 | 372 | all cold | 0 | 5,494,250 | 180 | 0 |
| eco-llm s4 / s5 / s6 | 20 / 24 / 20 | 0 | 372 / 370 / 372 | all cold | 0 | 5,579,984 / 5,622,934 / 5,593,834 | 345 / 1,065 / 405 | 0 |
| hybrid-F s4 / s5 / s6 | 20 / 24 / 20 | 0 | 372 / 370 / 372 | all cold | 0 | 5,301,776 / 5,317,513 / 5,324,320 | 345 / 1,065 / 405 | 0 |
| hybrid-F6 s4 / s5 / s6 | 20 / 24 / 20 | 0 | 372 / 370 / 372 | all cold | 0 | 5,236,808 / 5,261,188 / 5,227,930 | 345 / 1,065 / 405 | 0 |
| mooncake s4 / s5 / s6 | 15 / 21 / 15 | 0 | 372 / 370 / 372 | all cold | 0 | 5,479,025 / 5,556,227 / 5,486,424 | 285 / 735 / 180 | 0 |

It is a REAL OBSERVATION, not an instrument that never reads, and it is corroborated twice over
from outside the policy's own belief: the engine reports 0 prefix-cache hits against 5.2 to 5.6
million queries in every cell, and every robot request carries `cached_tokens` 0, which is the
engine's own per-request number rather than the coordinator's model.

The read sites, per the Step 2 rule (a quantity written and never read is ABSENT):

- `coordinator.py:575`, `cost = C.recall_gpu_s(tokens, s.residency_readiness())`. A real read: the
  residency sets the GPU seconds the request is charged.
- `cstate.py:525-526`, which builds `obs.cloud.gpu_warm_sessions` and `host_warm_sessions`, the
  lists an arm reads to learn what is warm.
- `coordinator.py:481`, `if s.built_tokens < s.est_tokens and s.believed_tier() != "gpu"`, in the
  build path.

ONE READ IS DEAD, and it is the one that would close the loop. `residency.jsonl` carries
`telemetry_cached_tokens`, written at `coordinator.py:901`, and it is NULL in every row of every
cell: 372 of 372, in all 13 cells. So the engine's own `cached_tokens` never reaches the belief,
and the belief is never contradicted by the thing it models. In these runs the belief happens to
be right, which is exactly the condition under which a dead validation read goes unnoticed.

Why the zero is unsurprising rather than suspicious: D84 gives every device its own cache salt, so
no prompt prefix is shared BETWEEN devices by design, and 12.4 shows the median robot history is
asked exactly one question, so there is almost no reuse available WITHIN a device either. The
warm-state axis is close to unexercised in this workload, which is a statement about the workload,
not about the policies.

### 12.3 What the committed delivery stamp is worth (definition audit, consistency check 4)

The runs were launched with `forward_at = "first"` (recorded in every `run_meta.json`), so an
answer is stamped delivered at its FIRST TOKEN plus a constant wire delay. That delay is exactly
0.022176 s in 13,558 of 13,558 answers of b7 n16 s4, which is why the "after first token" column
in 12.1 is a constant rather than a distribution. The generation that follows is real and is
charged to no deadline: `t_done - t_first_token` has p50 0.058 s and max 2.715 s in the same cell.

How many questions would change verdict if delivery were stamped at COMPLETION instead (MEASURED,
same files, same deadlines of 5 s robot and 2 s single-shot; a refused request counts as a miss
under D144):

| cell | type | n | on time (committed stamp) | on time (at completion) | flip |
|---|---|---|---|---|---|
| b7 n16 s4 | robot | 15 | 14 | 11 | 3 |
| b7 n16 s4 | single-shot | 356 | 332 | 329 | 3 |
| b7 n16 s5 | robot | 21 | 19 | 11 | 8 |
| b7 n16 s5 | single-shot | 356 | 320 | 309 | 11 |
| eco-llm n16 s4 | robot | 20 | 14 | 10 | 4 |
| eco-llm n16 s4 | single-shot | 356 | 294 | 288 | 6 |
| eco-llm n16 s5 | robot | 24 | 19 | 10 | 9 |
| eco-llm n16 s5 | single-shot | 356 | 304 | 293 | 11 |
| hybrid-F n16 s4 | robot | 20 | 15 | 15 | 0 |
| hybrid-F n16 s4 | single-shot | 356 | 339 | 339 | 0 |
| hybrid-F n16 s5 | robot | 24 | 21 | 20 | 1 |
| hybrid-F n16 s5 | single-shot | 356 | 343 | 343 | 0 |
| hybrid-F6 n16 s4 | robot | 20 | 14 | 13 | 1 |
| hybrid-F6 n16 s4 | single-shot | 355 | 334 | 334 | 0 |
| hybrid-F6 n16 s5 | robot | 24 | 21 | 19 | 2 |
| hybrid-F6 n16 s5 | single-shot | 356 | 342 | 342 | 0 |
| mooncake n16 s4 | robot | 15 | 14 | 11 | 3 |
| mooncake n16 s4 | single-shot | 356 | 332 | 326 | 6 |
| mooncake n16 s5 | robot | 21 | 19 | 11 | 8 |
| mooncake n16 s5 | single-shot | 356 | 319 | 310 | 9 |

This is a DEFINITION, not a defect: for an MCQ letter the first token IS the answer, and the
runner exposes the alternative as a flag. But the definition is load-bearing and it is not neutral
between arms. At seed 5 the committed stamp puts the robot column at hybrid-F 21, hybrid-F6 21,
b7 19, eco-llm 19, mooncake 19, a spread of 2; stamping at completion puts it at hybrid-F 20,
hybrid-F6 19, b7 11, eco-llm 10, mooncake 11, a spread of 9 or 10. The arms that throttle hold the
engine at a load where generation stays fast, and the committed stamp does not count that. Nothing
here says which stamp is right; it says the choice decides the size of the effect, and the arms
whose decode is slow are the baselines, so the current convention UNDERSTATES the policy arms.
RefSpatial is the case where the first token is certainly not the answer, since its answer is a
coordinate pair.

### 12.4 Reuse per robot history (item 3), 16 devices, seeds 4 to 6

| arm | robot sessions with questions | questions per history p50 / max | gaps measured | constructed warm-prefix token fraction p50 | constructed fraction with any warm prefix |
|---|---|---|---|---|---|
| b7-edf-feasibility | 51 | 1 / 3 | 14 | 0.9778 | 0.9608 |
| eco-llm | 51 | 1 / 3 | 14 | 0.9867 | 0.9688 |
| hybrid-F-lhreq | 51 | 1 / 3 | 14 | 0.9867 | 0.9688 |
| hybrid-F6-lhreq | 51 | 1 / 3 | 14 | 0.9867 | 0.9688 |
| mooncake | 51 | 1 / 3 | 14 | 0.9778 | 0.9608 |

MEASURED: the median robot history is asked ONE question, and only 11 to 14 same-history gaps
exist across 34 to 51 sessions, so there is almost no question-to-question reuse to capture.

CONSTRUCTED, and this is the interesting half: if every 30 s upload batch had been prefilled on
arrival, 97.8 to 98.7 percent of a question's history tokens would already have been in the cache
at question time, and 96.1 to 97.7 percent of questions would have had some warm prefix. The
reuse available in this workload is not ACROSS questions, it is WITHIN one history's own growth,
and nothing in the current setup prefills a batch before a question asks for it. The frame cadence
used per session is its own measured one (`t_opportunity / frames_on_the_wire`), and the batch size
is the 30 s the question names.

### 12.5 Warming budget (item 4)

Prefilling each 30 s batch of every robot history, charged with the committed COLD curve on the
batch's NEW tokens only (MODELLED), against the 62,944-token GPU pool and the 27 GiB host tier
(110,592 tokens at the committed 262,144 bytes per token):

| cell | robot devices | sessions | warming GPU-s | share of the 1200 s run | peak resident tokens | x GPU pool | x host tier | x GPU plus host | GiB |
|---|---|---|---|---|---|---|---|---|---|
| n16 s4 | 7 | 13 | 38.1 | 3.2 % | 119,075 | 1.89 | 1.08 | 0.69 | 29.07 |
| n16 s5 | 7 | 15 | 49.5 | 4.1 % | 166,659 | 2.65 | 1.51 | 0.96 | 40.69 |
| n16 s6 | 7 | 13 | 35.7 | 3.0 % | 139,581 | 2.22 | 1.26 | 0.80 | 34.08 |
| n18 PROJECTED | 8 | n/a | 43.5 | 3.6 % | 159,521 | 2.53 | 1.44 | 0.92 | 38.95 |

The 18-device row is a PROJECTION by robot-device count from the 16-device median, not a
measurement: no 18-device cell exists yet.

The GPU time is affordable and the memory is not. Warming costs 3 to 4 percent of the run's GPU
budget, while holding every robot history needs 1.9x to 2.7x the GPU pool and 1.1x to 1.5x the
host tier on its own; at seed 5 it is 96 percent of the GPU and host tiers combined, and the
projection at 18 devices is 92 percent. So a warming policy in this setting is a PLACEMENT and
EVICTION problem, not a compute problem, and the peak above is an upper bound that keeps every
history of every session that asked a question and ignores the sessions that never asked.

### 12.6 Cross-type value per GPU-second (item 5)

Committed tables, with the GPU-seconds MODELLED by the COLD curve on the measured median prompt of
that type in these cells:

| axis | gain | median prompt tokens | modelled GPU-s | gain per GPU-s |
|---|---|---|---|---|
| dashcam (C1 value) | 0.09000 | 378 | 0.0840 | 1.0714 |
| SS refspatial | 0.18742 | 1,372 | 0.3049 | 0.6147 |
| SS realworldqa | 0.08297 | 1,372 | 0.3049 | 0.2721 |
| robot LH-REQ EVAL | 0.28986 | 9,623 | 2.1384 | 0.1355 |
| robot LH-REQ DEV | 0.14286 | 9,623 | 2.1384 | 0.0668 |

A shedding rule that maximised gain per GPU-second would shed ROBOT RECALL FIRST, by a factor of 8
against dashcam frames and 4.5 against RefSpatial, because the robot gain is the largest per
QUESTION and the smallest per GPU-SECOND: it buys 0.29 of accuracy for 2.14 GPU-s while a dashcam
frame buys 0.09 for 0.084 GPU-s. That is the arithmetic a value-based shedding rule would act on,
and it points away from the mechanism this study exists to test.

THE UNITS DO NOT MATCH, and the ranking is therefore a CONVENTION, not a measurement. The robot
gain is an MCQ-accuracy difference, dashcam is a challenge-mAP value, RefSpatial is a point-in-mask
fraction and RealWorldQA is exact match. `ss_quality.json _metric_incomparability` already records
this for C1's ordering, and it binds here for the same reason: a column that adds them is a
convention about what we are willing to trade, not evidence about what is worth more.

### 12.7 Why hybrid-F sends the 33,839-token history that b7 declines (report only)

Every arm's decision for the same opportunity (opp0010837, robo002, session 1848337166005249,
arriving at t 957.90 with 33,781 tokens of history), MEASURED at 16 devices seed 0:

| arm | sent to cloud | representation | tokens charged | image parts on the wire | HTTP | letter | on_time as recorded |
|---|---|---|---|---|---|---|---|
| b7-edf-feasibility | no | n/a | n/a | n/a | n/a | n/a | n/a |
| mooncake | no | n/a | n/a | n/a | n/a | n/a | n/a |
| eco-llm | yes | RECENT | 467 | 375 | 400 | X | true |
| hybrid-F-lhreq | yes | RECENT | 467 | 375 | 400 | X | true |
| hybrid-F6-lhreq | yes | RECENT | 467 | 375 | 400 | X | true |

Corroborated on the dry path, same cell, where the decision counts are: b7 CLOUD 375, DEFER 2,
REJECT 5; mooncake CLOUD 375, REJECT 4, DEVICE 1; hybrid-F CLOUD 375 plus 5 CLOUD-at-RECENT;
eco-llm CLOUD-at-D2 375 plus 5 CLOUD-at-RECENT. The five rescued questions are the same five.

The chain, with the read sites:

1. b7 and mooncake REJECT it. The feasibility test predicts a COLD prefill of the whole 33,781
   tokens against a 5 s deadline, which fails `est <= slack + defer_s`
   (`baselines/constructed.py:184-191`), so the question is answered on the device and never
   reaches the cloud.
2. hybrid-F's C3 converts exactly that rejection into a send. `hybrid_arm.py:315-318`: when the
   question is not CLOUD and is not single-shot, C3 re-tests it at the 467-token recent window,
   which the same curve says is feasible, and emits CLOUD at representation RECENT. eco-llm
   rescues the same five questions the same way.
3. THE PROMISE REACHES THE ACCOUNTING AND NOT THE PAYLOAD. `coordinator.py:574` charges
   `tokens_for_representation`, which is 467 for RECENT, while `coordinator.py:593-597` builds the
   request body from `s.frames`, the whole session: 375 image parts went on the wire and the server
   refused the request with HTTP 400 at 33,839 tokens. C3's RECENT is expressible in the cost and
   UNEXPRESSIBLE in the request, which is the same shape as the write-only field with one read
   added.
4. The refusal was then recorded as an on-time cloud answer with the placeholder letter X, because
   `coordinator.py:781` computes `ontime = delivered <= o.deadline_abs()` from the completion time
   alone, with no reference to the status or to whether an answer was parsed. D144 ruling 3 makes
   it a miss; the H100 has applied that rule and republished the headline.

No code was changed for this subsection. The defect it names is in the harness, not in any arm:
the policy asked for a cheap representation, was charged for a cheap representation, and sent an
expensive one.

## 13. Dry pre-screen of every live2 arm (A6000, 2026-11-20, user request)

One dry cell per registered arm: 40:40:20 dashcam : LH-REQ EVAL robot : SS2 EVAL single-shot,
1200 s, seed 4, 16 devices, stub bridge, no engine. SCREENING ONLY, never a result for any arm.
Script `experiments/orchestration/live2/baseline_prescreen.py`, output
`results/orchestration/live2/frozen_test/baseline_prescreen.json`, distinct-arm list written to
`results/orchestration/live2/frozen_test/runs/PRESCREEN_DISTINCT_ARMS`.

**118 registered arms, 0 errors, 60 distinct decision logs, 18 groups of two or more, 24 arms
channel-silent.**

### 13.1 What "identical" means here, and what it does not

Arms are grouped by the digest of the decision log, positionally, so a group means byte-identity
including order. The register matters more than the number: this is an OBSERVED coincidence at ONE
cell, not a constructed proof that two arms are the same policy. A cell that never reaches an arm's
branch cannot distinguish it from an arm that has no such branch.

The sharpest instance is our own: **hybrid-F, hybrid-F6, hybrid-F6r and their four `-lhreq` and
four `-c6` twins are all byte-identical at this cell**, twelve names in one group. They are not the
same arm. C6 moves 3 decisions at 20 devices seed 0, F differs from F6 at five of the six smoke
cells, and the robot-only gate moves 2 robot and 82 dashcam decisions at 16 devices seed 0. Seed 4
at 16 devices is simply the one cell where C6 changes nothing. Any reader who takes the grouping as
a dedup list deletes the comparison the study exists to make, which is why the control file carries
that warning above the names.

### 13.2 The groups of two or more

| arms | members |
|---|---|
| 12 | b7-edf-feasibility, builder-default, builder-s1-fairshare, builder-s1-feasible, builder-s1-lateness, builder-s2-value, builder-s4-adaptive, builder-s4-llf, builder-s6-decline, **clockwork**, **ekya**, hybrid-base |
| 12 | hybrid-F, hybrid-F-c6, hybrid-F-lhreq, hybrid-F-lhreq-c6, hybrid-F6, hybrid-F6-c6, hybrid-F6-lhreq, hybrid-F6-lhreq-c6, hybrid-F6r, hybrid-F6r-c6, hybrid-F6r-lhreq, hybrid-F6r-lhreq-c6 |
| 6 | hybrid2-all-k05, hybrid2-all-k05-c6, hybrid2-c1c2k05c3c5, hybrid2-c1c2k05c3c5-c3always, hybrid2-c1c2k05c3c5-c3always-c6, hybrid2-c1c2k05c3c5-c6 |
| 5 | always-cloud-fcfs, **inar-vl**, **routellm**, **videostorm**, **vllm-priority** |
| 4 | hybrid2-all-k15, hybrid2-all-k15-c6, hybrid2-c1c2k15c3c5, hybrid2-c1c2k15c3c5-c6 |
| 4 | hybrid-c1c2k05, hybrid-c1c2k1, hybrid-c1c2k15, hybrid-c1c2k2 |
| 4 | hybrid-c1c2k1c3, hybrid-c1c2k1c3-c6, hybrid-c1c2k2c3, hybrid-c1c2k2c3-c6 |
| 4 | hybrid-base-c6, hybrid-c1-c6, hybrid2-c1c5-c6, hybrid2-c5-c6 |
| 4 | hybrid-c1c2k05-c6, hybrid-c1c2k1-c6, hybrid-c1c2k15-c6, hybrid-c1c2k2-c6 |
| 3 | **kvflow**, **pensieve**, **rh8-demand-aware-oracle** |
| 3 | hybrid-c1, hybrid2-c1c5, hybrid2-c5 |
| 3 | hybrid2-c1c2k05, hybrid2-c1c2k05c5, hybrid2-c1c2k05c5-reserve |
| 2 each | builder-acfcfs + builder-s2-all; hybrid-all-k1 + its -c6; hybrid-all-k2 + its -c6; confidence-cascade + **streamscout**; hybrid2-c1c2k05c5-c6 + hybrid2-c1c2k05c5-reserve-c6; hybrid2-c1c2k15c3c5-c3always + its -c6 |

Published arms are in bold. Three readings worth stating plainly, each about THIS cell:

1. **Eleven arms decide exactly as b7 does**, including two published systems, clockwork and ekya,
   and nine of our own builder and hybrid-base variants. For the published pair this is the
   port-side question in CLAUDE.md: the port is legal and fairly treated and decides nothing b7
   does not.
2. **Four published arms decide exactly as always-cloud-fcfs**, and that group is channel-silent,
   so those four sent everything to the cloud and used no other channel.
3. **The k_r ladder is inert at this cell**: k_r 0.05, 0.1, 0.15 and 0.2 give one log in the
   `hybrid-c1c2k*` family, and the same collapse appears in the c3 and -c6 ladders. The screening
   that chose k_r cannot have been decided by this cell.

### 13.3 Channel-silent arms (24 of 118)

An arm is channel-silent here when it emitted the two unavoidable release kinds and used no other
decision channel: no non-default representation, no deferral, no decline, no piece split, no tier
request. This is the port-side rule's question, asked of every arm at once.

always-cloud-fcfs, builder-acfcfs, builder-s2-all, hybrid-base-c6, hybrid-c1-c6, hybrid-c1c2k05-c6,
hybrid-c1c2k1-c6, hybrid-c1c2k15-c6, hybrid-c1c2k2-c6, hybrid-llm, hybrid2-c1c2k05-c6,
hybrid2-c1c2k05c5-c6, hybrid2-c1c2k05c5-reserve-c6, hybrid2-c1c2k15-c6, hybrid2-c1c2k15c5-c6,
hybrid2-c1c2k15c5-reserve-c6, hybrid2-c1c5-c6, hybrid2-c5-c6, inar-vl, routellm,
thinking-qwenvl-atdm, uniscale, videostorm, vllm-priority.

Six of the 24 are published arms (inar-vl, routellm, thinking-qwenvl-atdm, uniscale, videostorm,
vllm-priority). The rest are our own `-c6` variants, which is itself informative: a `-c6` variant
that is channel-silent while its base arm is not has had its base arm's channel removed rather than
extended, and that is worth a look before any of them is cited.

Three more arms are nearly silent in a different way: device-only, hybrid-llm and perllm emit 377
decisions against 13,570 for b7, so they release no dashcam frames to the cloud at all at this cell.

### 13.4 Characteristic decision, where it is declared

A single channel read for every arm is exactly the failure CLAUDE.md records, so the characteristic
is declared per arm from that arm's own description, and the other 112 arms are reported as
UNDECLARED with their full census rather than as zeros. An undeclared characteristic is not a zero.

| arm | characteristic decision | count at this cell |
|---|---|---|
| b7-edf-feasibility | feasibility actions (decline plus defer) | 5 |
| eco-llm | non-default representation per request | 377 |
| mooncake | state action (keep-warm retention) | 377 |
| hybrid-F-lhreq | non-default representation (C3's RECENT) | 5 |
| hybrid-F6-lhreq | non-default representation (C3's RECENT) | 5 |
| hybrid-F6r-lhreq | non-default representation (C3's RECENT) | 5 |

Every one is non-zero, so no arm in the live comparison fails the port-side rule. The hybrid count
is a FLOOR, not a census: C1 acts through `order`, C2 through the dashcam throttle and C5 through
the cap, and `decision.jsonl` carries none of those three channels, which is the same
unexpressibility that section 11.4 of `study_policy_f.md` records for C1.

## 14. Four-seed headline at 16 devices, and the second-cell exclusion check (A6000, 2026-11-20)

D144 items 1 and 2. Computed on this box from the committed run directories on origin, with no live
run touched. Script: `experiments/orchestration/live2/frozen_headline.py`, which is the H100's
seed-0/4/5 script extended rather than forked, so the two agree by construction where they overlap.
Output `results/orchestration/live2/frozen_test/frozen_headline_n16_4seed.json`.

What changed in the script: a local trace fallback, because this box does not hold the H100's trace
tree; a robot-on-time column over ALL questions beside the feasible one; and a per-run D133 verdict
with its margin in questions and a fragile flag.

CONTROLS before any number below is read.
- The regenerated traces reproduce the H100's robot opportunity ids EXACTLY at every seed, and the
  script refuses a run whose trace and outcomes disagree on the robot question set rather than
  scoring it on a guess.
- The feasible counts from the local traces, 18 / 15 / 22 at seeds 0 / 4 / 5, equal the committed
  `frozen_feasible.json` counts to the question.
- Restricted to seeds 0, 4 and 5 this script reproduces the H100's committed three-seed headline.

THE RUNS ARE PRE-FIX, and this is the limit on everything in 14.1 to 14.3. The RECENT defect
described in 12.7 was present in every eco-llm, hybrid-F and hybrid-F6 run scored here: 3 to 7
RECENT releases per run were charged 467 tokens and sent the whole session. The H100 has staged the
fix (a RECENT release will send the session's most recent k frames, k = ceil(frames x charged /
history tokens), every other representation byte-identical), and the completed runs cannot be
rescored for it; redoing them is the user's call. So these numbers describe the arms as they ran,
not the arms as they are now specified.

### 14.1 Pooled four-seed rates, paired by seed (B = 10,000)

On time = delivered within the deadline (robot 5 s, single-shot 2 s) by a request that returned
HTTP 200, per D144. The bootstrap resamples opportunities WITHIN each seed and applies the same draw
to every arm, so the arms stay paired on the same questions; differences against b7 use the same
draws.

| arm | robot feasible on time | CI95 | difference vs b7 | robot all on time | difference vs b7 | SS on time | CI95 | difference vs b7 | dashcam all-meet |
|---|---|---|---|---|---|---|---|---|---|
| b7-edf-feasibility | 64 / 69 = 0.9275 | [0.8551, 0.9855] | reference | 64 / 89 = 0.7191 | reference | 1306 / 1426 = 0.9158 | [0.9011, 0.9299] | reference | 4 of 4 |
| eco-llm | 62 / 69 = 0.8986 | [0.8261, 0.9565] | [-0.0725, 0.0000] | 62 / 89 = 0.6966 | [-0.0562, 0.0000] | 1191 / 1426 = 0.8352 | [0.8163, 0.8541] | **[-0.0954, -0.0666]** | 4 of 4 |
| mooncake | 64 / 69 = 0.9275 | [0.8551, 0.9855] | [0.0000, 0.0000] | 64 / 89 = 0.7191 | [0.0000, 0.0000] | 1304 / 1426 = 0.9144 | [0.8997, 0.9285] | [-0.0063, 0.0035] | 4 of 4 |
| hybrid-F-lhreq | 67 / 69 = 0.9710 | [0.9275, 1.0000] | [-0.0145, 0.1014] | 67 / 89 = 0.7528 | [-0.0112, 0.0899] | 1372 / 1426 = 0.9621 | [0.9516, 0.9719] | **[0.0316, 0.0610]** | 4 of 4 |
| hybrid-F6-lhreq | 65 / 69 = 0.9420 | [0.8841, 0.9855] | [-0.0435, 0.0725] | 65 / 89 = 0.7303 | [-0.0337, 0.0562] | 1356 / 1426 = 0.9509 | [0.9390, 0.9621] | **[0.0196, 0.0505]** | 4 of 4 |

Read the two columns that exclude zero and the three that do not.

**The single-shot column separates the arms and the robot column does not.** hybrid-F is +3.2 to
+6.1 pp over b7 on single-shot on time and hybrid-F6 is +2.0 to +5.1 pp, both excluding zero;
eco-llm is -9.5 to -6.7 pp, also excluding zero. On the robot pool, hybrid-F's +4.4 pp point
estimate carries a CI of [-1.5, +10.1] pp and hybrid-F6's [-4.4, +7.3] pp: at 69 feasible questions
pooled over four seeds, the robot comparison cannot resolve a difference of this size. Mooncake is
indistinguishable from b7 on every axis, exactly as section 4c's mechanism note predicts, since its
377 keep-warm state actions find nothing resident.

So the measured advantage of the frozen policy at 16 devices is on SINGLE-SHOT timeliness, which is
the device type C6 cannot act on and C3 is deliberately not applied to. The robot axis, which is the
axis the study is about, is unresolved at this fleet size.

**Every on-time robot question was a feasible one, in all 20 runs.** The robot-all hits equal the
robot-feasible hits in every single cell (17 / 17, 14 / 14, 19 / 19, 14 / 14 for b7, and so on), so
no arm ever answered an infeasible question on time. The feasibility rule is not merely a filter
here, it is a perfect predictor on these 89 questions, which is the strongest support the D133
headline choice has had, and also the reason the "all questions" column tracks the feasible one.

### 14.2 Per-seed detail, including the seed-6 feasible counts

| arm | seed 0 feas | seed 4 | seed 5 | seed 6 | SS per seed | errors per seed |
|---|---|---|---|---|---|---|
| b7-edf-feasibility | 17 / 18 | 14 / 15 | 19 / 22 | 14 / 14 | 317, 332, 320, 337 of 356, 357, 356, 357 | 1, 0, 0, 0 |
| eco-llm | 16 / 18 | 14 / 15 | 19 / 22 | 13 / 14 | 292, 294, 304, 301 | 1, 0, 0, 1 |
| mooncake | 17 / 18 | 14 / 15 | 19 / 22 | 14 / 14 | 319, 332, 319, 334 | 0, 0, 0, 1 |
| hybrid-F-lhreq | 17 / 18 | 15 / 15 | 21 / 22 | 14 / 14 | 341, 339, 343, 349 | 1, 0, 0, 0 |
| hybrid-F6-lhreq | 16 / 18 | 14 / 15 | 21 / 22 | 14 / 14 | 335, 334, 342, 345 | 1, 0, 0, 0 |

Seed 6 contributes 14 feasible robot questions of 20 asked, the smallest feasible pool of the four
seeds; seed 5 the largest at 22 of 25. Pooled, 69 feasible of 89 asked. D82's 20-question minimum
is met per run on ALL questions (20 to 25) and is NOT met per run on the feasible pool (14 to 22),
which is why the feasible column is pooled and never read per cell.

### 14.3 Per-run D133 verdicts, every one of them fragile

A verdict is marked FRAGILE when one question would change it. The bar is `p_rob` 0.9 from each
run's own sweep block, so meeting it needs `ceil(0.9 x feasible)` on time.

| arm | seed 0 | seed 4 | seed 5 | seed 6 |
|---|---|---|---|---|
| b7-edf-feasibility | meets, margin +0 | meets, +0 | **fails, -1** | meets, +1 |
| eco-llm | **fails, -1** | meets, +0 | **fails, -1** | meets, +0 |
| mooncake | meets, +0 | meets, +0 | **fails, -1** | meets, +1 |
| hybrid-F-lhreq | meets, +0 | meets, +1 | meets, +1 | meets, +1 |
| hybrid-F6-lhreq | **fails, -1** | meets, +0 | meets, +1 | meets, +1 |

**All twenty verdicts are fragile.** The feasible pools are 14 to 22 questions against a 90 percent
bar, so one question is worth 4.5 to 7.1 pp and no verdict in this table has more than one
question of slack. hybrid-F is the only arm that meets the bar at all four seeds, and it does so by
exactly one question at three of them. A per-run D133 verdict at this fleet size is a coin landing
on its edge, and nothing in this study should rest on one.

DEFINITIONS, because two "robot pool meets" flags disagree on purpose. The verdict above is over
the D133 FEASIBLE pool. The `robot_pool_meets` flag inside each run's own scorer block is over ALL
robot questions, which is 0.70 to 0.75 against the same 0.9 bar, so it is False in all 20 runs. Both
are correct for what they measure and they must never be quoted as one number.

### 14.4 Second-cell exclusion check (D144 item 2)

The pre-screen in section 13 ran one cell, and the sweep list then excluded arms as duplicates of
another arm on that one cell. This re-runs the identical screen at a SECOND cell, seed 0 instead of
seed 4, same workload, and asks whether each excluded arm is still identical. Output
`results/orchestration/live2/frozen_test/baseline_prescreen_seed0_exclusions.json`.

**Three of the fourteen exclusions were wrong.** At seed 0:

| arm | excluded as identical to | verdict at the second cell | decisions |
|---|---|---|---|
| clockwork | b7-edf-feasibility | **SEPARATES** | 13,621 against 13,623 |
| ekya | b7-edf-feasibility | **SEPARATES** | 13,621 against 13,623 |
| builder-s2-value | b7-edf-feasibility | **SEPARATES** | 13,621 against 13,623 |

Identical at BOTH cells, so a representative plus an identical list is sound:

| representative | identical at both cells |
|---|---|
| b7-edf-feasibility | builder-default, builder-s1-fairshare, builder-s1-feasible, builder-s1-lateness, builder-s4-adaptive, builder-s4-llf, builder-s6-decline, hybrid-base |
| kvflow | pensieve, rh8-demand-aware-oracle |
| always-cloud-fcfs | inar-vl, routellm, videostorm, vllm-priority |

clockwork and ekya are two PUBLISHED systems that a one-cell screen would have dropped from the
sweep. They are restored. Two cells are not all cells either, so the lists above are support for
the grouping, not proof of it, and that is why the grouping is recorded with the cells it was
measured on rather than as a property of the arms.

### 14.5 hybrid-F6r and hybrid-F6rm: built, measured, not run live (D144 item 3)

Both arms are registered in `hybrid_arm.py` and neither runs live: C6 is to be redesigned as a
counterfactual for warming and shedding, and hybrid-F6 results stand as built.

- **hybrid-F6r** gates BOTH C6 consumers to non-single-shot recall: the per-request `_c6_one` and
  the per-period policy-core mirror in `_c6_prepare`, which is where 94 percent of the cost was.
- **hybrid-F6rm** gates only the per-request call and keeps advancing the mirror every period, so
  its robot decisions are identical to hybrid-F6 by construction and it saves nothing.

Why the cheap one is not a speed fix (setwise decision diffs against hybrid-F6, dry, three-type
LH-REQ cells):

| cell | robot decisions moved | single-shot | dashcam | total |
|---|---|---|---|---|
| n=16 seed 0 | 2 | 0 | 82 | 84 |
| n=16 seed 4 | 0 | 0 | 0 | 0 |
| n=20 seed 0 | 0 | 2 | 1 | 3 |
| n=20 seed 4 | 3 | 1 | 142 | 146 |
| **n=32 seed 0** | **12** | **30** | **10,327** | **10,369** |
| n=32 seed 4 | 2 | 8 | 6 | 16 |

All six cells are in `results/orchestration/live2/hybrid/policy_f6r_proofs.json`, with the two
further proofs D144 ruling 4 asks for.

THE CHARACTERISTIC DECISION STILL OCCURS in hybrid-F6r, which a gate that merely silenced C6 would
also have satisfied on the diff table above: `c6_calls` 20 to 52 per cell, `c6_scorer_error` 0 in
all six cells, and every call on a period that holds non-single-shot recall (prepare calls equal
robot-period prepare calls in every cell).

WHAT THE GATE BOUGHT, and it is more than the 92 percent I estimated from the 16-device p50. Wall
time inside the policy-core mirror per 1200 s cell, dry on this box, so a cost of the mirror and not
a live latency:

| cell | hybrid-F6 mirror ms | hybrid-F6r mirror ms | cut | F6 C6 calls | F6r C6 calls |
|---|---|---|---|---|---|
| n=16 seed 0 | 21,517 | 153 | 99.3 % | 371 | 23 |
| n=16 seed 4 | 16,917 | 193 | 98.9 % | 354 | 20 |
| n=20 seed 0 | 56,884 | 424 | 99.3 % | 498 | 26 |
| n=20 seed 4 | 63,664 | 420 | 99.3 % | 376 | 24 |
| n=32 seed 0 | 145,901 | 1,398 | 99.0 % | 788 | 52 |
| n=32 seed 4 | 153,664 | 875 | 99.4 % | 701 | 39 |

So hybrid-F6 spends 17 to 154 seconds of every 1200 second cell inside the mirror, and the gate
removes 99 percent of it. That is the size of the prize the redesign is aiming at, and it is why
the gate is tempting; the diff table above is why it cannot be taken as a relabel.

THE DEVIATIONS ARE NOT A SUBSET, which settles the question by itself. At 32 devices seed 0,
hybrid-F6 deviates 42 times (35 `c6_dev_send_to_hold`, 7 `c6_dev_send_to_recent`) and hybrid-F6r
deviates 10, of which one is a `c6_dev_recent_to_hold` that hybrid-F6 never makes anywhere. A
restriction that produces a deviation KIND the unrestricted arm never produces is not the same
policy with fewer decisions.

`_c6_prepare`'s own docstring says it advances the mirror TO THIS PERIOD, so the mirror carries
state across periods: skip the single-shot-only periods and the mirror reaches the next robot period
having never seen them. The divergence grows with fleet size because the skipped periods grow with
it, and at 32 devices the gate moves ten thousand decisions. **hybrid-F6r is a third policy, not a
faster hybrid-F6**, and only hybrid-F6rm can carry the label "hybrid-F6 with C6 restricted to
robots". Both are recorded here so the redesign starts from the measurement rather than from the
assumption that the gate was free.

The measured cost the gate was meant to remove is in section 6.2: C6's mirror put the F6 arm 2x to
9x over the 100 ms decision period at p99 at every fleet size, with 94 percent of its calls on
single-shot requests. A redesign that keeps the mirror per period pays that; one that does not pays
a different policy. That is the trade the C6 redesign inherits.

D144 item 4, the offline analysis that drives the redesign, is section 12 and was committed earlier
(`c6b6a02`, refreshed in `3faa91e`).

## 15. Offline warm-state study (A6000, 2026-11-20, design input for the C6 redesign)

CPU only, committed traces, no engine, no policy code, no arm. Script
`experiments/orchestration/live2/warm_state_offline.py`, output
`results/orchestration/live2/frozen_test/warm_state_offline.json`.

Section 12 established that no robot question in the entire grid was ever served warm (0
prefix-cache hits against 5.2 to 5.6 million queries per cell, `cached_tokens` 0 on every robot
request), that robot misses are dominated by history prefill, and that prefilling each 30 s upload
batch on arrival would have had 97.8 to 98.7 percent of a question's history in cache. This asks the
next two questions: under real memory capacities, how much of that is keepable, and how much does
choosing WHICH history to keep add over keeping the recent ones.

REGISTERS. **MEASURED: nothing here.** TRACE: session starts and ends with their declared durations,
the 30 s history batches with their own token counts, and each robot question's history tokens and
deadline, all from the committed trace (regenerated locally; the same regeneration reproduced the
H100's robot opportunity ids exactly, section 14). MODELLED: every time and cost, from the committed
curves (`costs.recall_ttft_s`, `recall_gpu_s`, StudyRH5). CONSTRUCTED: the policies, the capacities
below the committed pair, and the oracle.

The composition rule, the one modelling choice that is not just the committed curve: a history of h
tokens with c of them resident at tier X costs `recall_ttft_s(c, X) + recall_ttft_s(h - c, "COLD")`,
which reduces to the committed warm number at c = h and the committed cold number at c = 0. The
HOST-WARM curve already includes the reload, so a host hit is charged its reload.

Three ways the simulation is GENEROUS, so the numbers read as an upper bound on warming's value
rather than a prediction: the whole GPU pool and host tier are given to robot histories (in the live
runs they also hold the dashcam and single-shot working set); a batch prefill is charged its GPU
seconds but never queues; and on-time is TTFT against the 5 s deadline, with a second column adding
section 12.1's measured 0.74 s p50 of waiting plus queueing, with decode excluded in both.

POLICIES. **P0** no warming, as the grid ran. **P1** warm every batch, evict least recently used,
GPU to host to cold. **P2** warm every batch, evict the lowest P(question within T), T in 60, 120,
300 s. **P3** oracle: keeps the histories whose next question is soonest, an upper bound that reads
the future.

P2's hazard is fitted on SEED 0 only, which is not in the evaluation set (seeds 4, 5, 6), so fit and
score never share data (D6): two rates, 3.026e-3 per second for a session not yet asked (34 first
questions over 11,235 s of exposure) and 2.516e-3 for one already asked (14 later questions over
5,565 s). The horizon is clipped by the session's own declared remaining life, which `session_start`
carries. That clipping is what makes T read anything at all: with a two-rate hazard and no clipping
the ranking is monotone in the rate alone, every T gives the same order, and the parameter is inert.
P2 therefore uses one thing LRU does not have, the session's declared end, and that is an assumption
about what a deployed policy would know rather than a free lunch.

### 15.1 Results at 16 devices, seeds 4, 5, 6 pooled (65 robot questions)

Tier columns are where the question found its history. TTFT and on-time are MODELLED.

| capacity | policy | GPU | host | cold | TTFT p50 | p90 | on time of 65 | warming GPU-s per 3 cells |
|---|---|---|---|---|---|---|---|---|
| 1.00x | P0 (as run) | 0 | 0 | 65 | 2.607 | 5.621 | **51** | 0 |
| 1.00x | P1 LRU | 41 | 24 | 0 | 0.613 | 0.908 | **65** | 271 |
| 1.00x | P2 T=60 | 58 | 7 | 0 | 0.576 | 0.851 | **65** | 271 |
| 1.00x | P2 T=120 / 300 | 54 | 11 | 0 | 0.576 | 0.852 | **65** | 271 |
| 1.00x | P3 oracle | 65 | 0 | 0 | 0.562 | 0.829 | **65** | 317 |
| 0.50x | P0 | 0 | 0 | 65 | 2.607 | 5.621 | 51 | 0 |
| 0.50x | P1 LRU | 20 | 30 | 15 | 0.652 | 3.827 | **60** | 1,774 |
| 0.50x | P2 T=60 | 38 | 24 | 3 | 0.589 | 0.955 | **64** | 801 |
| 0.50x | P2 T=120 | 36 | 25 | 4 | 0.589 | 0.955 | 63 | 784 |
| 0.50x | P2 T=300 | 26 | 36 | 3 | 0.623 | 0.955 | 63 | 761 |
| 0.50x | P3 oracle | 65 | 0 | 0 | 0.562 | 0.829 | **65** | 924 |
| 0.25x | P0 | 0 | 0 | 65 | 2.607 | 5.621 | 51 | 0 |
| 0.25x | P1 LRU | 4 | 19 | 42 | 1.867 | 5.574 | **54** | 2,431 |
| 0.25x | P2 T=60 | 15 | 25 | 25 | 0.656 | 5.574 | **55** | 1,765 |
| 0.25x | P2 T=120 | 16 | 22 | 27 | 0.656 | 5.621 | 53 | 1,773 |
| 0.25x | P2 T=300 | 11 | 21 | 33 | 1.647 | 5.621 | 53 | 1,717 |
| 0.25x | P3 oracle | 37 | 28 | 0 | 0.562 | 0.944 | **65** | 1,837 |

**18 devices is the same table, exactly.** At 40:40:20 both 16 and 18 devices give SEVEN robot
devices (16 is 6 dashcam, 7 robot, 3 assistive; 18 is 7, 7, 4), so the robot sessions, batches and
questions are identical and the robot-side simulation cannot differ. That is worth stating for the
grid as well as for this study: moving from 16 to 18 devices buys ZERO additional robot questions,
it only adds dashcam and single-shot load.

Why the two on-time columns are identical in every row: no question's modelled TTFT lands in the
0.74 s window the queue allowance moves across (`in_queue_flip_window` is 0 in all 36 cells). The
TTFT distribution is bimodal, a few hundred milliseconds when warm and seconds when cold, so the
allowance has nothing to flip. The column is reported rather than dropped so that an equality is not
mistaken for a copy.

### 15.2 The control, which is the only thing tying this to reality

P0 is the condition the grid actually ran, so its modelled on-time is checkable against the measured
one. MODELLED 51 of 65. MEASURED at the same seeds: hybrid-F 50, hybrid-F6 49, b7 47, mooncake 47,
eco-llm 46 of 65. The model is optimistic by 1 question against the best arm and 4 against b7, in
the direction its own exclusions predict, since it charges no queueing and no decode. A model that
reproduced the measurement exactly would be the suspicious outcome here; one that is optimistic by
exactly the terms it leaves out is behaving.

### 15.3 What this says for the redesign

**1. At the committed capacity, warming closes the robot deadline completely and selection adds
nothing.** P0 51 of 65 becomes 65 of 65 under every warming policy, recovering all 14 misses, and
the P1 to P3 gap is ZERO questions. At 1.0x the histories simply fit: peak residency is 62,736 to
62,916 GPU tokens against the 62,944 pool with the remainder on host, so an LRU that keeps
everything is already optimal. The cost is 271 GPU-s across three 1200 s cells, 90 per cell, 7.5
percent of one cell's GPU budget.

**2. Selection is worth something only under memory pressure, and then it is worth a lot.** The P1
to P3 gap is 0 questions at 1.0x, **5 questions at 0.5x** (P1 60, P3 65) and **11 questions at
0.25x** (P1 54, P3 65). P2 captures 4 of the 5 at 0.50x (64 of 65) and 1 of the 11 at 0.25x. So a
cheap two-rate hazard plus a declared session end recovers most of what selection can give at half
capacity and almost none of it at quarter capacity, where the ranking problem gets hard.

**3. LRU thrashes, and the cost lands on the GPU budget.** Warming GPU-seconds for P1 rise from 271
to 1,774 to 2,431 across the three capacities, 9x, while the questions it saves fall from 14 to 9 to
3. At 0.25x that is 810 GPU-s per 1200 s cell, 68 percent of the budget, to recover 3 questions of
14, because a history demoted to cold is re-prefilled from scratch at its next batch. P2 does the
same work for 1,765 GPU-s and P3 for 1,837 with all 14 recovered, so **at tight capacity the
difference between selection policies is mostly a difference in wasted prefill, not in hit rate.**

**4. A shorter horizon is better, which is a design answer and a small one.** Under pressure T = 60
beats T = 300 by 1 question at 0.50x and 2 at 0.25x, and the ordering is the same at every capacity.
The parameter only reads anything because it is clipped by the session's declared remaining life, so
the useful signal here is NOT the length of the horizon, it is knowing when a session is over.

### 15.4 A MEASURED control that arrived after the simulation, and it inverts the reading

While this section was being written the H100 ran `edf` and `llf`, the first two arms of the
scheduling sweep. Both EMIT HISTORY BUILDS (359 and 363 of them at 16 devices seed 4, one per
session) where the five frozen-grid arms emit none, so for the first time in this study a robot
question meets a warm prefix. Everything in this subsection is MEASURED from those runs.

**The warming mechanism works, and by more than the model said.** All 16 of edf's warm robot recalls
were preceded by a build on the same session, so the build is what put the prefix in the cache.

| arm | robot requests | cache_path | cached fraction p50 | MEASURED TTFT p50 | mean | max |
|---|---|---|---|---|---|---|
| edf | 16 | WARM | 0.988 | **0.384** | 0.331 | 0.461 |
| edf | 3 | COLD | 0 | 4.448 | 4.945 | 6.257 |
| llf | 12 | WARM | 0.986 | **0.423** | 0.347 | 0.525 |
| llf | 3 | COLD | 0 | 4.568 | 4.961 | 6.247 |
| b7-edf-feasibility | 15 | COLD | 0 | 2.440 | 2.710 | 5.409 |
| hybrid-F-lhreq | 20 | COLD | 0 | 3.100 | 3.626 | 7.291 |

Against section 15.1's MODELLED numbers this is a clean pass in the conservative direction: modelled
warm TTFT p50 0.562 to 0.613 s against 0.384 to 0.423 s measured, and modelled cold 2.607 s against
2.44 to 3.10 s measured. The model understates the warm gain and lands on the cold cost.

**And the arm that gets the warm prefixes has the WORST robot on-time of the four.** Robot questions
on time at 16 devices seed 4: hybrid-F 15 of 20, b7 14, llf 10, **edf 5**. Decomposed as in 12.1:

| arm | wait before release p50 / max | queue residual p50 | prefill (modelled on measured uncached) p50 | arrival to delivered p50 | on time |
|---|---|---|---|---|---|
| edf | **5.483 / 11.741** | 0.376 | 0.027 | 6.839 | 5 of 20 |
| llf | 1.986 / 5.074 | 0.420 | 0.027 | 4.360 | 10 of 20 |
| b7-edf-feasibility | 0.115 / 0.156 | 0.530 | 1.824 | 2.617 | 14 of 20 |
| hybrid-F-lhreq | 0.104 / 0.333 | 0.538 | 2.277 | 3.238 | 15 of 20 |

edf's prefill is 0.027 s, essentially free, and its questions still miss, because each one WAITS
5.5 s at the median and up to 11.7 s before release, which is longer than the entire 5 s deadline.

**WHY it waits, measured rather than assumed.** An earlier draft of this subsection said the
questions queue behind the build traffic. That is WRONG and the right answer is sharper. edf emits
2,697 `defer` decisions where b7 emits none, 36 at the median per robot question and up to 42, and a
robot question is released **0.003 s at the median AFTER the last build completion for its own
session** (min -0.003 s, max 352 s). With `session_MATERIALIZE` 360 and `release_whole` 360 in the
same run, the sequence is: the question arrives, the cold prefill of its history is predicted to
miss the deadline, so the arm defers it in 0.5 s steps while materializing that session's history,
and releases it the instant the materialization lands. The engine queue residual over the same
questions is 0.376 s, so the engine was never the bottleneck.

**So edf warms REACTIVELY, at the question, and the question pays the whole warming latency.** That
is a different failure from the one I first wrote down, and it does not show that warming costs
on-time. It shows that WHEN you warm decides who pays: warming on demand puts the materialization
inside the deadline, warming ahead of arrival does not. The offline policies P1 to P3 all warm ahead
of arrival on batch events, so none of them has this cost, and edf is not a measurement of them.

What the live cells therefore do and do not control for in section 15. They DO confirm the
mechanism and the magnitudes: a build makes the next question on that session warm, and warm is
0.384 s against 2.44 to 3.10 s cold, better than the model's 0.562 s. They do NOT yet test the
model's second generosity, that warming is charged GPU-seconds but never queues, because in these
two arms the warming was serialised with the question by the arm's own deferral rather than
competing with it. Section 16 builds that contention in explicitly and calibrates it here.

Two things this does NOT say. It does not say edf's release discipline is warming's fault: edf is
plain EDF with no feasibility admission, so it releases badly in general, and the 5.5 s wait is a
property of the arm as much as of its builds. And it does not say the five frozen-grid arms could get
the warm prefixes for free: they emit no builds at all, so for them the warm path was never
reachable, which is what 12.2 measured.

SCOPE CORRECTION TO 12.2, which said no robot question in the grid was ever served warm. That is
exact for the five frozen-grid arms over the 13 cells it names, and it is NOT true of the grid as a
whole now that edf and llf have run: 16 of 19 and 12 of 15 of their served robot questions were warm
at 96.6 percent cached. The warm-state axis is not unexercisable in this harness; it is unexercised
by the arms that emit no builds.

**5. The honest limit of all five points.** The median robot history is asked exactly ONE question
(section 12.4), so every policy above is choosing what to keep for a single future event per
session, and the oracle's advantage is almost entirely the advantage of knowing which sessions those
are. A warming policy in this workload is a prediction problem about sparse one-shot demand, not a
caching problem about reuse. That is the shape the C6 redesign has to address, and it is the opposite
of what a counterfactual chooser tuned on repeated access would assume.

## 16. Warming that competes for the GPU, calibrated on the live cells (user addendum, 2026-11-20)

Section 15 charged warming its GPU-seconds and never queued it, which section 15.4 showed is the
exclusion that matters. This part builds the contention in: every request and every warming prefill
goes through one shared server model, and two warming DISCIPLINES are compared under every placement
policy. Script `experiments/orchestration/live2/warm_state_contention.py`, output
`results/orchestration/live2/frozen_test/warm_state_contention.json`.

**W1** warms immediately on arrival: a prefill joins ONE FIFO with deadline work, so a prefill that
arrived first holds a slot the next question waits for. **W2** warms only into spare capacity:
strict priority for deadline work, and a prefill may not start while anything queued is at risk,
using the policy's own committed test, laxity below 0.3 times the deadline (D143 ruling B). A prefill
is never preempted once started, because a prefill is not resumable. Placement policies are section
15's P1 LRU, P2 at T = 60 s and P3 oracle, with P0 (no warming) as the floor.

### 16.1 Calibration against the live edf and llf cells, and what it is worth

Two numbers, and only one is fitted.

**f, the interference factor, FITTED.** The committed curve gives a request's GPU-busy time in
isolation; measured TTFT at this load is larger because the engine batches. Fitted as the ratio of
measured median TTFT to modelled service on the two WARMING-FREE arms: **dashcam 3.18, single-shot
1.47, robot recall 1.38**. That the dashcam factor is the largest is itself informative: a 378-token
frame spends most of its TTFT waiting its turn inside the batch, not computing.

**c, the slot count, MEASURED not fitted.** The engine's own concurrency in the same cells, the sum
of measured TTFT over the run length: 7,008 s over 1,200 s, so **c = 5**.

Fit quality, with the two warming arms as pure validation (modelled over measured, so 1.00 is
perfect):

| arm | role | dashcam | single-shot | robot | build |
|---|---|---|---|---|---|
| b7-edf-feasibility | fit | 1.02 | 1.00 | 1.03 | n/a |
| hybrid-F-lhreq | fit | 0.98 | 1.00 | 1.03 | n/a |
| edf | **validation** | 0.99 | **0.27** | **1.38** | **0.65** |
| llf | **validation** | 1.00 | **0.26** | 0.95 | **0.66** |

**Where the fit holds and where it does not, stated rather than averaged.** Dashcam service
transfers to the validation arms within 1 percent, and llf's robot recalls within 5 percent. The
three bad cells are all on the WARM side, which is exactly the side the fit could not see: f was
fitted on arms whose every request is cold, so a warm single-shot request is modelled at 0.087 s
against 0.316 s measured (x0.27) and a build at 0.293 s against 0.448 s (x0.65). **So this model
UNDERSTATES the cost of warm service and of warming itself by roughly 1.5x on builds and 3.7x on
warm single-shot.** Every W1-versus-W2 difference below is therefore a LOWER BOUND on the contention
a real engine would show, and the on-time levels are not predictions: the model gives P0 43 of 65
robot questions against 46 to 50 measured, and 1,070 of 1,070 single-shot against 1,306 of 1,426
measured, because single-shot service here is one fixed prompt size with no decode. **Read the
columns against each other, never as levels.**

### 16.2 Results, 16 devices, seeds 4, 5, 6 pooled (65 robot, 1,070 single-shot)

| capacity | policy | W | robot on time | warm | robot queued (p90 / max s) | SS on time | SS queued (p90 / max s) | warming GPU-s |
|---|---|---|---|---|---|---|---|---|
| 1.00x | P0 | none | 43 / 65 | 0 | 9 (0.014 / 0.063) | 1070 / 1070 | 145 (0.021 / 0.153) | 0 |
| 1.00x | P1 | W1 | **65 / 65** | 65 | 10 (0.024 / 0.063) | 1070 / 1070 | 153 (0.023 / 0.157) | 271 |
| 1.00x | P1 | W2 | **65 / 65** | 65 | 10 (0.024 / 0.063) | 1070 / 1070 | 153 (0.019 / 0.157) | 271 |
| 1.00x | P2 / P3 | W1, W2 | 65 / 65 | 65 | 10 to 13 | 1070 / 1070 | 153 to 154 | 271 to 317 |
| 0.50x | P1 | W1 | 55 / 65 | 48 | 18 (0.054 / 0.486) | 1062 / 1070 | 328 (0.154 / **3.746**) | 1,764 |
| 0.50x | P1 | W2 | **56 / 65** | 49 | 20 (0.057 / 0.198) | **1069 / 1070** | 320 (0.118 / 1.589) | 1,756 |
| 0.50x | P2 | W1 | 63 / 65 | 62 | 12 (0.030 / 0.417) | 1068 / 1070 | 194 (0.053 / 2.116) | 801 |
| 0.50x | P2 | W2 | 63 / 65 | 62 | 12 (0.030 / 0.417) | 1068 / 1070 | 194 (0.049 / 2.046) | 801 |
| 0.50x | P3 | W1 | 65 / 65 | 65 | 13 (0.033 / 0.129) | 1070 / 1070 | 210 (0.056 / 1.083) | 924 |
| 0.50x | P3 | W2 | 65 / 65 | 65 | 13 (0.033 / 0.096) | 1070 / 1070 | 209 (0.053 / 0.902) | 924 |
| 0.25x | P1 | W1 | 47 / 65 | 22 | 23 (0.122 / 0.711) | 1059 / 1070 | 388 (0.264 / **3.746**) | 2,433 |
| 0.25x | P1 | W2 | 47 / 65 | 22 | 25 (0.087 / 0.491) | **1068 / 1070** | 383 (0.157 / 1.625) | 2,433 |
| 0.25x | P2 | W1 | 49 / 65 | 40 | 16 (0.072 / 0.491) | 1064 / 1070 | 309 (0.116 / 2.360) | 1,763 |
| 0.25x | P2 | W2 | 49 / 65 | 40 | 17 (0.072 / 0.491) | 1066 / 1070 | 303 (0.094 / 2.046) | 1,763 |
| 0.25x | P3 | W1 | **65 / 65** | 65 | 19 (0.080 / 0.711) | 1066 / 1070 | 303 (0.092 / 2.515) | 1,830 |
| 0.25x | P3 | W2 | **65 / 65** | 65 | 20 (0.080 / 0.491) | 1068 / 1070 | 302 (0.087 / 2.046) | 1,832 |

### 16.3 What the contention actually costs

**1. At the committed capacity there is no contention to manage.** Robot on-time is 65 of 65 under
every policy and both disciplines, 10 of 65 questions queue at all, and the worst wait in the whole
cell is 63 ms. The GPU has spare slots: deadline work needs about 3.1 of the 5 and warming 0.2 more.
**W1 and W2 are indistinguishable on outcomes here**, differing only in the single-shot queue p90
(0.019 s against 0.023 s). The binding resource at 1.0x is MEMORY, which is what section 15 found,
and adding GPU contention does not change that conclusion.

**2. Under memory pressure the discipline starts to pay, and it pays on SINGLE-SHOT, not robots.**
At 0.50x with LRU, W2 buys 1 robot question (56 against 55) and **7 single-shot questions (1,069
against 1,062)**, and cuts the worst single-shot queue wait from **3.746 s to 1.589 s**. At 0.25x it
buys 0 robot and **9 single-shot** (1,068 against 1,059), with the worst wait 1.625 s against
3.746 s. The reason is the deadline asymmetry: a single-shot request has 2 s and a robot 5 s, while a
warming prefill occupies a slot for 0.3 to 0.9 s, so an immediate prefill is a serious fraction of a
single-shot budget and a minor one of a robot's. **Warming traffic injures the tightest deadline
class first**, which is the class C6 was already unable to help (section 6.2).

**3. Why pressure creates contention at all, when the GPU is the same size.** Warming GPU-seconds
rise from 271 at 1.0x to 1,764 and 2,433 at 0.50x and 0.25x for LRU, because evicted histories are
re-prefilled, so the memory limit manufactures GPU load. At 0.25x that is 811 GPU-s per 1,200 s
cell. **Contention here is a SYMPTOM of thrashing, not an independent cost**, and the way to avoid it
is to keep the right histories, not to schedule the prefills better: P2 at 0.50x reaches 63 of 65
with 801 GPU-s where P1 reaches 55 with 1,764.

**4. Selection still dominates discipline.** At 0.50x, switching LRU to the hazard policy is worth 7
to 8 robot questions; switching W1 to W2 is worth 1. At 0.25x the oracle is worth 16 to 18 robot
questions over P2 and the discipline 0. If the redesign can afford one mechanism, it should be the
choice of WHAT to keep, not the scheduling of WHEN to prefill it.

**5. The one place the discipline is not optional.** W1's worst single-shot queue wait is 3.746 s
against a 2 s deadline, so an immediate-warming policy does not merely miss a few single-shot
deadlines, it misses them by more than the deadline itself. Given that the calibration understates
warm and build service by 1.5x to 3.7x (16.1), a real engine would show this worse than the table
does. **W2 is the safe default and W1 should not be built**, even though at the committed capacity
the two are equivalent: the cost of W1 appears exactly in the regime a deployment would hit first,
which is memory pressure.

## 17. KV-reuse debug: why prefix_cache_hits is 0 (A6000, 2026-11-20, user request)

OFFLINE. Committed request logs, committed metrics snapshots and committed code only. No GPU, no
model server, nothing touched on the H100, which was running StudySH-EP throughout. Worked example
`eco-llm_n16_s4_1200s_h27_3t`, cross-checked against its postfix twin and `hybrid-F-lhreq` at the same
cell.

**The answer in one line: the server was configured correctly and the workload has almost no reusable
prefix, and the three places where it does have one are separated by enough traffic to turn the KV pool
over at least twice.** No flag needs changing and nothing on the server needs fixing for this.

### 17.0 One definition first, because it changes the size of the puzzle

`prefix_cache_queries_total` counts **tokens queried, not requests**. This run's committed snapshot
delta is **5,579,984** and the sum of `prompt_tokens` over its 13,562 requests is **5,604,554**, which
agree to 0.4 percent, the snapshot window omitting the first and last ten seconds. So "0 of about 5.5M
queries" is 0 of 5.5M tokens offered over 13,562 requests, not 5.5M missed reuse opportunities. The
number of requests that had any earlier request to reuse at all is **3**.

### 17.1 The server was configured for reuse, and one cache proves it worked

Each run's own `header.json` records the server's full argv at `server.command`, 37 elements for this
cell. It passes `--no-enable-prefix-caching` at element 13 and `--enable-prefix-caching` at element 27,
and `--limit-mm-per-prompt` twice, at 14 and 20, with `--mm-processor-cache-gb` at 29. Last occurrence
wins in argparse, so prefix caching was ON, the image cap was the later 640 and the multimodal
processor cache was ON at 128 GB. The metrics agree: a disabled prefix cache does not report 5.6M
queries. `experiments/dashcam/sh_ep_server_h100.sh` reproduces the same command byte for byte, which is
how this section first recovered it, but the run record is the better citation and is used here.

**The multimodal cache hit exactly as often as it could have, which rules out the uuid path.** From the
committed `mm_gate.json`: `mm_cache_queries` 16,342 and `mm_cache_hits` **345**. Counting image-part
references in the request log gives 16,407 references over 16,062 distinct uuids, so **345 references
beyond the first**, and no uuid is referenced more than twice.

| quantity | from the request log | from the server's counters |
|---|---|---|
| image-part references | 16,407 | 16,342 queries (window omits ~20 s) |
| references beyond the first | **345** | **345 hits** |

Exact agreement. The D84 uuid mechanism resolves every repeated frame to a cache hit and never misses
one. So the multimodal path is not where the KV zero comes from, and this also corrects a reading I
sent the H100 earlier in the day: I had grepped `mm_cache_hits_total=0` out of the early snapshots and
generalised it to the run. The run's delta is 345, not 0, and the H100 was right to ask for the gate
file.

### 17.2 What the request stream actually offers

| requests | share | what two consecutive ones share |
|---|---|---|
| 13,186 single-frame dashcam monitors, all 378 tokens, one image each | 97.2 % | the chat wrapper and the header only, which is on the order of 12 to 18 tokens, against vLLM's 16-token block. Measurably zero blocks: 13,186 requests produced no hit |
| 376 recall requests over 373 sessions | 2.8 % | 370 sessions hold exactly ONE request |

So **3 requests in 13,562 have any earlier request on the same history**, and a perfect cache could have
hit on 3. All 16 cache salts are constant per device, one each, so the salt breaks nothing.

### 17.3 The three real opportunities, and why each was certainly evicted

All three are append-only with the same salt and the same leading frame refs in the same order, at 90
tokens per recall frame. The GPU KV pool is **62,944 tokens**, which is 3,934 blocks of 16.

| session | reuse on offer | separated by | pool turnover between them |
|---|---|---|---|
| robo004 s000, r1270 to r5281 | 60 frames, about 5,400 tokens | 350.0 s, 4,010 requests, 1,653,204 tokens | **26.3x** |
| robo002 s001, r7330 to r7719 | 180 frames, about 16,200 tokens | 34.1 s, 388 requests, 160,955 tokens | **2.6x** |
| robo003 s001, r7585 to r9532 | 105 frames, about 9,450 tokens | 170.0 s, 1,946 requests, 789,896 tokens | **12.5x** |

The whole run pushes 5,604,554 prompt tokens through a 62,944-token pool in 1,200 s, **89 pool
turnovers**. Even the closest pair has 2.6 turnovers between its two requests. Eviction before reuse is
not a hypothesis here, it is arithmetic, and it is the same mechanism section 15 measured offline: this
is the P0 no-warming case with LRU, observed on the real engine.

### 17.4 (b) Is the full-history body append-only?

**Append-only for every representation except RECENT.** `coordinator.py:606` builds the whole body as
`refs[idx0:]` with `idx0 = 0`, and the piece path (`:558`) sends `s.frames[:already]` as uuid-only
references followed by the new refs, so frames are never re-selected and never resampled: a longer
history is the shorter one plus a suffix, in the same order. The request log confirms it from the other
side, since the three repeated sessions share their leading uuids exactly.

**The one exception is prefix-breaking by construction**, and it is new. The RECENT-send fix of
2026-11-20 (`coordinator.py:597-604`) sets `idx0 = len(refs) - k`, so a RECENT release sends a **moving
suffix window** of the history. Its first frame changes as the session grows, so it shares nothing with
the full-history body beyond the header. That is the right behaviour for the charge it models, and it
is worth recording that it also forecloses prefix reuse for those requests. Count in the postfix cell:
`recent_window_sends` **5**, against 0 pre-fix.

### 17.5 (c) Does the harness abort late requests, or evict anything deliberately?

**No, and no.** There is no `abort` and no `.cancel(` anywhere in `experiments/orchestration/live2/*.py`.
The HTTP timeouts are 600 s (`asyncbackend.py:107`, `backend.py:85`), far above any request in this run,
so no request is dropped for lateness: a late request is scored late, not cancelled.

The only `evict` in the live2 tree is the **simulated** one. `cstate.enact_placement` counts
`offloaded / kept_warm / evicted / resident`, and `run_live2_real.py:52-53` says in terms what those
counts are: "Output-only: total enact_placement's per-call counts, which cstate returns and discards, so
a run records whether --kv-capacity-enforced ever evicted anything. **No decision reads it.**" So the
policy's model of KV residency never touches the engine's actual cache. Nothing in the harness evicts
anything from vLLM, and the eviction that produced the zero is vLLM's own LRU under the turnover in
17.3.

### 17.6 Most likely cause, and what the H100 should check when the grid server next comes up

**Cause, in order of contribution.** (1) 97.2 percent of requests are single-frame monitors with less
than one block of shared prefix, so most of the run cannot hit by construction. (2) The robot side
offers 3 reuse opportunities in 13,562 requests, because 370 of 373 sessions hold a single request.
(3) All 3 are separated by 2.6 to 26.3 pool turnovers, so they were evicted before reuse. Together
these account for the zero completely, with no server defect required.

**What is still worth one check, and it is small.** The arithmetic says those 3 were evicted, but it
does not prove the block hashes would have matched had they survived. When the frozen-grid server is
next up, and only then, the cheap test is a **back-to-back** pair rather than a forensic one: send one
recall body, then immediately resend it with one frame appended, same salt, same device, nothing in
between, and read `cached_tokens` on the second. StudySH-EP has in effect already run that test on the
same build and it passes, with `cached_tokens` 3,056 to 6,768 on appended requests, so the expected
result is a hit, and a miss would be the only genuinely new information available here.

Worth looking at on the server side when convenient, none of it implicated by the evidence above:
`--kv-offloading-backend native --kv-offloading-size 27`, in case the offload connector changes block
reuse.

**A correction to a recommendation this section first made.** It said the duplicated
`--no-enable-prefix-caching` then `--enable-prefix-caching`, and the two `--limit-mm-per-prompt`,
"should be reduced to a single flag" whenever the launcher is next edited. That was written without
checking what the flag list is, and the H100 pointed out what it is.
`experiments/orchestration/study_live2_pilot.py:80-83` builds the list from `E.COMMON` and then
**refuses to start** unless it matches the committed `DE_c38` server's flags element for element, with
only the host-tier size allowed to differ: `if diff != [("38", host_gib)] or len(ref) != len(flags):
raise SystemExit`. Deduplicating the list is therefore not a tidy-up of a launcher, it is a change to
the pinned configuration that every frozen-grid and sweep cell has run under, and it would also trip
the equality check itself. Under CLAUDE.md that is a methodological change and needs a ruling before
it is applied, not an edit at the next convenient moment. The StudySH-EP launcher copies the round-1
command byte for byte on purpose and stays as it is.

The underlying concern stands and is recorded here rather than acted on: the configuration is correct
today only because argparse takes the last occurrence, so a future reordering of a pinned list could
silently disable prefix caching in a run that would still look entirely normal. The cheap mitigation
that does NOT touch the pinned list is to record the engine's own RESOLVED cache setting beside the
argv.

A second correction, also the H100's, also to something this section asserted without checking.
It said no run record states the cache configuration. **The argv is recorded**, per run, at
`header.json` `server.command`, which is where 17.1 now cites it from; what is absent is the resolved
value, and `header.json`'s `server` block has no field of that kind. So a reader CAN establish from a
committed run that prefix caching was on, by applying the last-occurrence rule to the recorded argv,
and this section's first draft recovered the command from a launcher script when it could have read it
from the run directory it was already analysing. The residual gap is narrower than claimed and worth
closing anyway: one field carrying the engine's own `enable_prefix_caching=True` from its init log,
next to the argv, would spare every future reader the argparse reasoning on a list that deliberately
contradicts itself. That is a record addition rather than a pinned-list change, so it does not need
the ruling the dedup does, and the H100 will add it when a grid server next starts.

**What this is NOT.** It is not evidence that prefix caching fails on this engine, and it must not be
cited that way: the same build hits on appended requests in StudySH-EP. It is evidence that **the
frozen grid's own traffic has essentially no reuse to find**, which is a statement about the workload
and about the 62,944-token pool, and it is the live counterpart of section 15's finding that memory, not
the GPU, is the binding resource.
