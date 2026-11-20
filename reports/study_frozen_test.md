# StudyFROZEN-test (H100, overnight 2026-11-19 to 20): frozen-policy test, StudySS1-32B and SS timing

**Status: IN PROGRESS. Last updated 2026-11-19 19:45.** Rules: D116 (no methodological change overnight; never seeds 1
to 3 or HOLDOUT; never INVALID results; GPU 2 exclusive; no em dashes). PROVISIONAL decisions are marked.

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

## 5. Incidents

- 17:10 to 17:16: the first StudySS1-32B attempt failed every request (cache_salt '/'), stopped, no answers written.
- Host Python while the StudySS1 server was measuring idle TTFT: a py_compile and short edit or read scripts (seconds
  each), recorded here; no measured request overlapped a heavy process.
