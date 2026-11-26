# ROBOT QUESTION SAMPLING, QUESTION-CLUSTERED BOOTSTRAP, AND TOUCH VALUE (2026-11-26T15:50Z). CPU, committed cells, report only; the sampler was not changed and no cell was run. Computed by an analysis agent (not re-run by the main session); positive control: its cbd (cell.json robot_rows standing_correct_by_deadline; an independent outcomes+request+device_answers classifier agrees on 132 of 132 rows in 5 cells) reproduces rung 3 s4 83, q5c 83 (1x) and 74 (halved), q2m 85, q4 85, q5b 83.
## 1a. Question structure per seed (rung 3 1x; all arms see the same questions at a seed)
| seed | asks | distinct ids | max asks per id | median | mean | top-3 share of asks |
|---|---|---|---|---|---|---|
| s4 | 132 | 20 | 16 | 5.5 | 6.60 | 0.326 |
| s5 | 127 | 25 | 13 | 4 | 5.08 | 0.283 |
| s6 | 121 | 20 | 17 | 6 | 6.05 | 0.314 |
| s7 | 105 | 22 | 15 | 3 | 4.77 | 0.390 |
Rung 3 cbd per ask share, clustered 95 percent CI: s4 0.629 (0.382, 0.837); s5 0.441 (0.252, 0.661); s6 0.504 (0.248, 0.720); s7 0.476 (0.233, 0.684): **a single seed's cbd carries a wide question-level interval.**
## 1b. cbd difference, rung 3 minus arm, CLUSTERED by question id (distinct ids resampled with all their asks, 2,000 reps, seeded with the seed) against the ordinary ask-level bootstrap
**Ask-level CIs exclude 0 in all 20 baseline cells and are 2 to 3.4 times narrower than the clustered ones; ignoring clustering turns 15 of 20 cells whose clustered CI includes 0 into apparent wins. The clustered CI excludes 0 in 6 of 20: s4 simplestream and the five s6 arms.**
| 1x cells | diff (clustered 95% CI) | includes 0 |
|---|---|---|
| s4 simplestream | +64 (30, 101) | no |
| s4 cascade, mooncake, eco-llm | +34 (0, 70) | lower bound exactly 0 |
| s4 llf | +31 (-2, 65) | yes |
| s5 (all five baselines) | +17 to +18 (-15 to -9, 44 to 48) | yes, all |
| s6 cascade 7, simplestream 20, llf 12, mooncake 11, eco-llm 17 | +41 to +54 (lower bounds 4 to 13) | no, all |
| s7 | +15 to +20 (lower bounds -6 to -3) | yes, all |
Plain `covex-v6-base` at 1x rq30 is ABSENT at s4 to s7 (the base cells on origin are kv0.5r and kv0.5r_h0.5). **Base against rung 3 at HALVED memory (the D250 condition):**
| seed | kv0.5r diff (clustered CI) | kv0.5r_h0.5 diff (clustered CI) |
|---|---|---|
| s4 | +19 (-6, 42) | +11 (2, 22) |
| s5 | +11 (-17, 36) | +10 (-3, 23) |
| s6 | +28 (-1, 57) | +17 (3, 33) |
| s7 | +10 (-7, 36) | **-1 (-8, 7)** |
s4 variants of rung 3 (clustered): q5c 1x 0 (-3, 3), halved -2 (-13, 12); q5b 0 (-3, 3), halved +2 (-4, 10); q2m -2 (-5, 0), +3 (-8, 17); q4 -2 (-5, 0), +5 (-11, 23); q4b +1 (-2, 6), +9 (-5, 26); q5 +10 (2, 22) at 1x (excludes 0), +9 (-1, 24) halved. **Every q-variant difference at s4 is inside the question-level interval, except q5 at 1x (where rung 3 is better).**
## 1c. Where the question draw is set (code, read only; only the s4 plain trace and the s4 perframe_rq30 directory carry trace.jsonl.gz and trace_meta.json on origin; seeds 5 to 7 carry only dashcam_instants and device_answers, so their join offsets, session durations and re-ask times are not checkable)
- **The pool is NOT drawn per seed and is 69 questions in 51 sessions, not 97:** `lh_req_sessions()` (`fleet/data_sources.py:468-492`) fixes it as LH-REQ ids intersected with EVAL (the committed `lh_req_definition.json` has n 97 with EVAL 69 and DEV 28; trace_meta s4: pool_n 69, session_pool_n 51). **CORRECTION: my earlier notes said "20 to 25 questions drawn from the 97-question pool"; the generator's pool is the 69 EVAL questions.**
- **The per-seed draw is the SESSION dealing:** `rng_sess = random.Random(f"{seed}|sessions")` (`fleet/trace.py:597`) feeds `_deal(sorted(sessions), want_sess, rng_sess)` (:612), a distinct-first round-robin (:345-368); `want_sess = int(run_s/mean_sess_s)+3` per robot (:608). The join draw is `rng_join = Random(f"{seed}|join")` (:599), `join_frac = U[0, 0.5)` per robot (:634); the first session is joined at that point (:805-806); questions before the join are skipped and counted in `robot_questions_before_join` (:902-905). Each session holds about 1.35 LH-REQ questions on average, so the distinct originals per seed are 20, 25, 20, 22 (s4 to s7), no id shared between devices, per-device spread 1 to 5.
- **Asks per id** come from the re-ask block (`fleet/trace.py:953-1030`), on when `robot_reask_mean_s > 0` (rq30 inferred to be 30 s): RNG `Random("reask|%d|%s|%s" % (seed, dev, sid))` (:995), gaps `expovariate(1/30)` from the first original ask (:999), the re-asked question uniform over those already asked (:1006), so EARLY questions collect the most re-asks; window to `min(session end, run_s)` (:990).
- **Why the totals differ (132, 127, 121, 105):** total = originals + re-asks = 20 + 112, 25 + 102, 20 + 101, 22 + 83. Re-ask volume depends on how long each robot's sessions with asks run after the first ask (sessions with asks 17, 17, 17, 13); s4 join offsets run from 7 s to 150 s (D101); per-device asks are uneven (s4 robo004 32; s7 robo002 32; s7 robo006 15 asks from ONE original). **The s5 to s7 numbers are NOT checked against a trace_meta (absent).**
## 2. Touch value: cold robot questions (cached/prompt < 0.5, cloud-requested robot rows), s4
| cell | cbd | cloud-requested | COLD | on time | late | median uncached (cold) | TOUCH chosen / issued |
|---|---|---|---|---|---|---|---|
| rung 3 1x | 83 | 132 | 18 | 14 | 4 | 5,987 | 2,674 / 2,674 |
| q5b 1x | 83 | 132 | 18 | 13 | 5 | 6,646 | 647 / 647 |
| q5c 1x | 83 | 132 | 19 | 13 | 6 | 6,695 | 32 / 32 |
| q4 1x | 85 | 132 | 17 | 13 | 4 | 5,703 | 10,901 / 10,866 |
| q4b 1x | 82 | 132 | 18 | 12 | 6 | 5,987 | 11,576 / 11,576 |
| q2m 1x | 85 | 132 | 17 | 13 | 4 | 5,703 | 1,336 / 1,336 |
| rung 3 halved | 72 | 98 | 34 | 16 | 18 | 10,527 | 1,434 / 1,371 |
| q5b halved | 70 | 99 | 33 | 13 | 20 | 11,483 | 1,029 / 999 |
| q5c halved | 74 | 118 | 37 | 12 | 25 | 13,927 | 363 / 178 |
| q4 halved | 67 | 122 | 38 | 13 | 25 | 10,670 | 3,877 / 3,107 |
| q4b halved | 63 | 124 | 36 | 10 | 26 | 13,246 | 5,268 / 4,131 |
| q2m halved | 69 | 115 | 39 | 15 | 24 | 11,752 | 375 / 285 |
(`-q5`: 1x 17 cold, halved 26, no touches.) **At 1x the cold count is 17 to 19 in every arm although TOUCH ranges from 32 to 11,576; at halved memory it roughly doubles to 33 to 39 (cold-late 18 to 26) in every touch-running cell. Touch volume does not move the cold-question count.**
**NO-TOUCH ABLATION EXISTS: `covex-v6-fair-final-notouch`** (`experiments/orchestration/live2/arms_v6notouch.py`; one-factor ablation row in `results/INDEX.md` D234 (2), note in `results/orchestration/live2/d233_stateoff/`): the planner is on and its touches are chosen but not enacted (s4 1x: state_touch_chosen_not_enacted 2,633, submitted_touch 0); it is NOT the `-stateoff` arm. Cells on origin: 1x at s4 to s7 and `kv0.5r` at s4 to s7; **NO `_kv0.5r_h0.5` no-touch cell.** cbd no-touch against rung 3, 1x then kv0.5r: s4 84/83 and 82/82; s5 56/56 and 58/54; s6 61/61 and 58/59; s7 50/50 and 50/50. Every clustered CI includes 0 (the s5 kv0.5r ask-level CI excludes 0 at (-8, -1), no-touch higher); s4 1x no-touch cold 18 (13 on time, 5 late), median uncached 5,987. **Reading: touches do not move the cold-question count or cbd at 1x or at kv0.5r; no test of touches at h0.5 exists.**
## CHECK 7 / DEFINITION FLAG (found in this job): the D250 seed batches are the HALVED condition
The agent's rung 3 totals: 1x s5 56, s6 61, s7 50 (the `_L3_epg_rq30` cells); `_kv0.5r_h0.5_..._preD249` halved s4 72, s5 52, s6 41, s7 40. **The "rung 3 cbd 52 (s5) and 41 (s6)" that the H100 reported for the D250 batches and that I recorded in the seed file and the morning summary are the HALVED-memory cells (D250 = the `_kv0.5r_h0.5` condition, as at s4: rung 3 72).** The records did not name the condition; the condition is added in research/study_d250_overnight_seed_verdicts.md and the morning summary (section 9). It does not change the verdicts as reported, but it changes what they speak to: **the D250 verdicts are HALVED-MEMORY verdicts.**
