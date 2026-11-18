# StudyMOT1-dayinlife: one robot rebuild in a monitored dashcam fleet (motivation, claim 6)

Status: amendment 1 COMPLETE 2026-11-18 09:58; **amendment 3 COMPLETE 13:21 (section 11): at light load chunked rebuilds serve both the fleet and the robot; the best action differs in each cell of the 2 x 2; the host-warm HOST prediction at the tight host failed (PARTIAL 4, COLD 1).** **Amendment 2 COMPLETE 11:04 (section 10): a history prepared host-warm
is served from the host with a roomy (256 GiB) host tier, costs the fleet nothing and answers in 0.69 s, but with the
tight 27 GiB host it is already cold by the question (5 of 5 runs, as predicted).** First design STOPPED AT N SELECTION (09:20); amended by the user
(section 0) and rerun 09:30 to 09:58. **One cold 11k rebuild done in one go makes all 20 monitored dashcams miss
deadlines: a median 57 extra missed instants and a 5.5 s burst in which more than half the fleet misses; 2,048-token
pieces cut that to 24 and 1.0 s; 1,024-token pieces remove it entirely (0 extra misses in 5 of 5 repetitions); the
robot pays for it: its answer arrives 3.5 s after the question in one go, 5.9 s with 2,048 pieces, 6.8 s with 1,024
pieces.** The pre-registered rule (largest N in {8, 16, 24, 32} whose
NONE run is >= 99 % on time; STOP if N = 8 is below 99 %) fired: N = 8 was 11.7 % on time. No main run was made; there
is no figure data. Pre-registered in research/EXPERIMENTS.md (StudyMOT1-dayinlife) before any run.

## 0. Amendment 1 (recorded 2026-11-18 ~09:30, BEFORE the rerun)

Reason: the first design sent one request per 0.5 s per stream, which at every N in the grid (8 to 32) exceeded the
32B's committed one-frame closed-loop peak of 15.1 requests/s (StudyD7b): a planner design error, not a property of
the question. User ruling: capacity-based monitoring (D62, D71). Each dashcam's decision instants stay on the 0.5 s
CTRL1c grid, and the cloud is sent EVERY 4TH INSTANT of each dashcam (one request per 2 s per stream, the 25 %
per-device service share of D71); the deadline is unchanged (0.916 s, submit to last token, server side); stream send
phases are staggered uniformly over the 2 s period (seeded). New N grid: 8, 12, 16, 20 streams (4, 6, 8, 10
requests/s). The N-selection rule is unchanged: the largest N whose NONE control is >= 99 % on time; STOP if N = 8
fails. Everything else (actions, repetitions, pairing, measures, sanity, figure data) is as pre-registered; the 0.5 s
bins now hold the sent instants that fall in them, and a bin's fraction is missed / sent. The failed first-design N
selection stays below as the first section of results.

## 1. Design as run (first design)

Server: the StudyLIVE2-pre Part 2 round-1 command (vLLM 0.31.0, 32B @0cfaf481, prefix caching ON, GPU pool 62,944, host
offload 27 GiB; flag diff vs ENG1c DE_c38 `[('38', '27')]`), started 09:07:44 (startup 63.8 s), stopped after the N
selection. Host tier filled at start with 7 fresh ~26k histories (189,488 tokens, 1.7x the 110,592-token capacity), the
ENG1c / ENG1e steady-state convention. Dashcams: N streams, each a different seeded Nexar clip from the 300-clip set
(next seeded clip when one ends), one monitoring request per 0.5 s per stream with the stored q90 JPEG and the live
monitoring body (`live2/bodies.build_body(kind="monitor")`: the StudyD3 body verified in LIVE2-pre, with stream,
stream_options, a per-stream cache_salt and a per-image uuid), starts staggered uniformly over the first 0.5 s, fresh
namespace per run. Deadline: ON TIME if submit-to-last-token <= 0.916 s (the 1.0 s target minus the D75 network
allowance: about 0.040 s frame upload at 13.6 Mbit/s plus 0.044 s RTT). Runner `experiments/motivation/
study_mot1_dayinlife.py` (request-harness client, asyncio + httpx).

## 2. Results, first design: N selection (NONE, 60 s, one run each)

| N | offered load (requests/s) | on time | e2e p10 / median / p90 (s) | HTTP errors | max client dispatch lag (s) |
|---|---|---|---|---|---|
| 8 | 16 | 112 / 960 = **11.7 %** | 0.87 / 1.71 / 2.52 | 0 | 0.06 |
| 16 | 32 | 16 / 1,920 = 0.8 % | 7.5 / 33.6 / 59.1 | 0 | 0.13 |
| 24 | 48 | 14 / 2,880 = 0.5 % | 13.8 / 63.8 / 117.9 | 10 (ReadError) | 4.90 |
| 32 | 64 | 10 / 3,840 = 0.3 % | 19.9 / 80.3 / 179.3 | 35 (ReadError) | 6.54 |

Every request had 378 prompt tokens and 0 cached tokens (fresh images), and produced 2 completion tokens.

**Why it failed.** The committed closed-loop peak of the 32B for one-frame requests is 15.1 requests/s (StudyD7b, the
`PEAK[1]` StudyE10b and StudyENG1 use). At the 0.5 s cadence every stream offers 2 requests/s, so N = 8 already offers
16 requests/s, above the server's capacity: the queue grows for the whole window (median e2e 1.7 s at N = 8, tens of
seconds beyond). The harness was not the bottleneck at N = 8 (dispatch lag at most 0.06 s, 0 errors). Every N in the
pre-registered grid lies above capacity, so the grid cannot select a feasible fleet on this hardware at this cadence.

## 3. What a feasible design would need (for the user; nothing was changed)

At 2 requests/s per stream, the 99 % on-time requirement needs a load well below the 15.1 requests/s peak; ENG1's
episodic loads P25 / P40 (25 % / 40 % of peak, 3.8 / 6.0 requests/s) kept TTFT around 0.25 s. That corresponds to about
N = 2 to 3 streams at a 0.5 s cadence, or N = 8 at a cadence of about 1.3 to 2 s. Choosing a new grid or cadence is a
methodological change and is the user's decision.

## 4. Sanity and consistency

0 HTTP errors at N = 8 and 16; 10 and 35 ReadErrors at N = 24 and 32 (connections dropped under a growing queue);
no robot request was sent (N selection precedes the main runs). Cross-check: the 15.1 requests/s peak (StudyD7b) and
ENG1's episodic TTFT at P25 / P40 are consistent with the overload observed; no INVALID result was used.

## 6. Results, amended design (one cloud request per 2 s per stream)

Server started 09:30:02 (startup 66.8 s), host filled to 189,488 tokens (1.7x the 110,592-token capacity), stopped
09:57:52. Runs 09:32 to 09:57; 0 HTTP errors in every run; maximum client dispatch lag 0.04 s.

**N selection (NONE, 60 s):**

| N | requests/s | on time |
|---|---|---|
| 8 | 4 | 240 / 240 = 100 % |
| 12 | 6 | 360 / 360 = 100 % |
| 16 | 8 | 480 / 480 = 100 % |
| 20 | 10 | 600 / 600 = 100 % |

Rule: the largest N with >= 99 % on time, **N = 20** (10 requests/s, 66 % of the 15.1 requests/s peak).

**Main runs, N = 20, 5 repetitions x 4 actions, paired within a repetition.** Every NONE control was 600 / 600 on time
(no INVALID repetition). Robot histories (one EVAL question per repetition, seeded): 11,367 / 11,831 / 10,160 / 10,743 /
10,159 prompt tokens; the robot's first request was cold in every run (0 cached tokens).

| action | extra missed instants, median (per repetition 1..5) | longest burst with > 50 % of streams missing, s | last extra miss after the question, s | streams with >= 1 extra miss | robot TTFT from the question, s |
|---|---|---|---|---|---|
| ONE-GO | **57** (63, 62, 57, 55, 53) | **5.5** (6.5, 6.0, 5.5, 5.5, 5.0) | 6.5 (7.0, 7.0, 6.5, 5.5, 6.0) | **100 %** (all 5) | **3.47** (4.98, 3.65, 3.47, 3.24, 3.29) |
| PIECES 2048 | **24** (26, 27, 24, 20, 19) | **1.0** (1.5, 1.0, 1.5, 1.0, 0.5) | 5.5 (6.0, 6.0, 5.0, 5.5, 5.0) | 75 % (95, 75, 85, 65, 50) | **5.90** (5.90, 6.36, 5.41, 5.96, 5.24) |
| PIECES 1024 | **0** (0 in all 5) | **0** | none | **0 %** | **6.79** (6.90, 7.25, 6.79, 6.46, 6.45) |

Pieces: 5 to 6 pieces of 23 frames (2048) and 11 to 12 pieces of 11 frames (1024); each piece's own TTFT 0.50 to 0.59 s
(first 2048 piece) and 0.26 to 0.40 s (first 1024 piece); the last piece (with the question) was submitted 4.0 to 5.2 s
(2048) and 5.7 to 6.5 s (1024) after the question. In other words the robot's answer time with pieces is the sum of
the per-piece round trips, each waiting behind the monitoring traffic, which is why it rises by 2.4 to 3.3 s rather
than the expected 0.5 to 1 s.

Representative repetition for the figure: repetition 3 (its ONE-GO extra-miss count, 57, is the median of the 5).
Figure data: `results/motivation/mot1/mot1_figdata.json` (per 0.5 s bin, the fraction of sent instants that missed, for
each action over the 60 s window; question at 20 s; each action's robot TTFT; the summary with per-repetition values).
Check plot (report only): `results/motivation/mot1/mot1_check.png`. Misses begin in the 19.5 to 20 s bin because
instants sent just before the question still have their 0.916 s deadline running when the rebuild occupies the engine.

## 7. Sanity checks

| check | result |
|---|---|
| NONE on time >= 99 % in every repetition | 100 % in 5 of 5 |
| 0 HTTP errors | 0 in all 24 amended runs |
| robot first request cold (cached <= 16) | 0 cached in all 15 action runs |
| ONE-GO robot TTFT within 0.8x to 1.25x of ENG1f's cold 11k under load (2.88 to 2.95 s at P25 / P40) | median 3.47 s = 1.19x: inside; repetition 1 alone is 4.98 s (1.70x): it was the first long request this server ever served (repetition 1 runs NONE then ONE-GO first), which is the first-long-request warm-up StudyENG1c Part E documented; the other four are 3.24 to 3.65 s |

## 8. Results consistency check

1. Cross-check: ONE-GO robot TTFT 3.47 s vs ENG1f cold 11k under P25 / P40 2.88 / 2.95 s (1.18 to 1.20x; the background
   here is 10 requests/s against 3.8 / 6.0) and vs ENG1 unloaded cold 2.74 s (1.27x); P2048 / ONE-GO extra misses 0.42,
   in line with ENG1e's chain2048 / mono imposed-delay ratios (0.15 to 0.52); P1024 0 extra misses where ENG1e's
   chain1024 imposed 8 to 26 % of mono's latency sum: a deadline miss needs > 0.916 s, and the delay a 1,024-token piece
   adds to a neighbour (one step of about 0.2 s, ENG1e) stays below the margin; P1024 rebuild 6.5 to 7.2 s vs ENG1e mode
   A chain1024 job completion 3.9 to 5.5 s (1.2 to 1.8x; heavier background here). No disagreement over 2x.
2. Physical plausibility: 11k tokens in about 3.3 s under load is about 3,400 tokens/s, below ENG1's unloaded prefill
   rate; nothing faster than committed curves.
3. Distribution sanity: all five per-repetition values reported for every measure.
4. Definition audit: deadline 0.916 s submit-to-last-token (section 0); pieces by ENG1c's d_job rule; bins of 0.5 s on
   the send time with fraction = missed / sent.
5. Claim linkage: motivation claim 6 (a cold history rebuild on the shared accelerator costs other devices their
   deadlines, and execution granularity trades that against the requester's own latency): supported by measurement.
6. Proxy validity: "on time" is measured server-side (submit to last token) with the network allowance subtracted from
   the target, not emulated per link; stated as such.

## 9. Files

New: `experiments/motivation/study_mot1_dayinlife.py`, `experiments/motivation/mot1_analyse.py`,
`reports/study_mot1_dayinlife.md`, `results/motivation/mot1/` (`mot1_requests.jsonl.gz` (both designs; labels NSEL* /
first design, A1* / amended), `mot1_runs_design1.json`, `mot1_runs.json` (amended), `mot1_results.json`,
`mot1_figdata.json`, `mot1_check.png`, `mot1_server.json`, `mot1.log`). Changed: `research/EXPERIMENTS.md`, `results/INDEX.md`,
`research/STATUS.md`.

Implementation note found while preparing the rerun (no effect on the first design's verdict): the dense Orin instant
set is on a 0.25 s grid (StudyD14b), so the first design sent consecutive 0.25 s instants every 0.5 s of run time
(each clip played at half speed). That changes which frame a request carries, not the offered load, which is what
failed. The amended runner takes the CTRL1c 0.5 s grid (t a multiple of 0.5 s) and sends every 4th instant, so a
stream's clip time advances 2 s per request, in step with run time.

## 10. Amendment 2: warm history (recorded 2026-11-18, BEFORE any amendment-2 run)

User prompt of 2026-11-18. Purpose: add the LOCATION dimension. Same scene as amendment 1 (20 dashcams, one cloud
request per 2 s each, deadline 0.916 s submit-to-last-token, server side; one robot question at t = 20 s needing its
~11k D2 history). Expected from StudyENG1 / ENG1c (not a constraint): a host-warm recall imposes almost nothing on the
dashcams and the robot answers in about 0.2 to 0.4 s.

**New action HOST-WARM.** Before the 60 s window starts (so no setup traffic falls inside it): (1) prefill the robot's
history in its run namespace: one request, max_tokens 1, the same frames, header, cache salt and uuids as the ONE-GO
body, without the question (a history prefill; the question part is then computed at the question, as for a real
recall); (2) fresh filler (new image namespace, ~26k-token D2 histories) totalling about 70,000 prompt tokens, more than
the 62,944-token GPU pool, so the history's blocks leave the GPU but, by the ENG1c rule (host-warm iff tokens written
since last use < host capacity), stay in the host tier; (3) at t = 20 s the full history plus the question is re-sent
as ONE request, the ONE-GO body, so any cached prefix is reused. The tier actually served is MEASURED at the question:
the request's cached tokens and the server's prompt-token-by-source counters (local cache hit vs external KV transfer)
read immediately before and after it (the ENG1c Part C / ENG1f method; the dashcam requests in flight use fresh images,
so they add no cache hits to those counters). Each run is labelled by the measured tier, never by intention: GPU if
local hits cover at least half the prompt; HOST if external transfers cover at least 90 % of the cached tokens and the
cached tokens cover at least half the prompt; PARTIAL if external transfers exceed 64 tokens otherwise; COLD otherwise.

**PART A: tight host (27 GiB, amendment 1's server exactly), 5 repetitions (amendment 1's seeds, clips and robot
sessions), HOST-WARM only.** PREDICTION, fixed now: writes after the history's last use by question time = filler
(~70k) + 20 s of dashcam traffic (20 streams x 0.5 requests/s x 20 s x 378 tokens = 75,600) = about 146k tokens, above
the 27 GiB host capacity (110,592 tokens), so the history is predicted COLD at the question in every run despite the
preparation. Measured tier vs prediction is reported per run.

**PART B: roomy host (256 GiB; the same server command with only --kv-offloading-size changed), 5 repetitions (same
seeds), actions NONE, ONE-GO, PIECES 2048, PIECES 1024, HOST-WARM**, order balanced within a repetition (odd r: NONE,
ONE-GO, P2048, P1024, HOST-WARM; even r: reversed), fresh namespaces per run (HOST-WARM's history namespace is fresh
too; only its preparation warms it). Checks: B's NONE controls >= 99 % on time (else INVALID, rerun once); B's ONE-GO /
PIECES medians within 0.8x to 1.25x of amendment 1's (host size should not matter for cold actions, StudyENG1c Part E),
ratios reported and anything outside investigated. STOP if B's HOST-WARM measures anything but HOST in 2 or more
repetitions, before writing figure data. Host tier filled at each server start to 1.5x its capacity (the amendment-1
convention). Measures as amendment 1 plus the measured tier and the robot request's cached tokens. Figure data:
`results/motivation/mot1/mot1_figdata_amend2.json` (Part B, all five actions, the representative repetition = the
one whose ONE-GO extra-miss count is the median of B's 5; Part A's per-run measured tier and outcome as a separate
block).

### 10.1 Amendment 2 run record

Part A: server 27 GiB (flag diff vs DE_c38 `[('38', '27')]`), started 10:13:39, host filled to 189,488 tokens (1.7x the
110,592-token capacity), runs 10:15 to 10:23. Part B: server 256 GiB (only `--kv-offloading-size` changed: diff
`[('38', '256')]`), started 10:23:30 (startup 160.8 s), host filled to 1,572,965 tokens (1.5x the 1,048,576-token
capacity, 59 fresh histories, 8 min), runs 10:35 to 11:04. N = 20 (amendment 1), amendment 1's seeds, clips and robot
sessions. 0 HTTP errors in all 30 runs; every Part B NONE control 600 / 600 on time (no INVALID run).

HOST-WARM preparation, every run: history prefill 10,001 to 11,711 prompt tokens with 0 cached (cold, as intended),
then 80,886 tokens of fresh filler (three ~27k histories, the smallest whole-history total above 70,000), finished 0.5 s
before the window opened.

### 10.2 Part A: tight host (27 GiB), HOST-WARM only

Writes after the history's last use by the question: 80,886 (filler) + 20 s of dashcam traffic (about 75,600) = about
156,500 tokens > 110,592.

| repetition | predicted tier | measured tier | robot cached / prompt tokens | robot TTFT (s) | missed instants | vs amendment 1's NONE of the same repetition |
|---|---|---|---|---|---|---|
| 1 | COLD | **COLD** | 0 / 11,367 | 3.58 | 45 | +45 |
| 2 | COLD | **COLD** | 0 / 11,831 | 2.91 | 55 | +55 |
| 3 | COLD | **COLD** | 0 / 10,160 | 2.58 | 43 | +43 |
| 4 | COLD | **COLD** | 0 / 10,743 | 2.62 | 44 | +44 |
| 5 | COLD | **COLD** | 0 / 10,159 | 2.54 | 40 | +40 |

The prediction held in 5 of 5: under this traffic a history prepared host-warm does not survive the 20 s to the
question when the host tier is 27 GiB, and the question then costs what a cold one-go rebuild costs (the last column
compares with a NONE run on another server instance, amendment 1's, and is a reference, not a paired difference).

### 10.3 Part B: roomy host (256 GiB), all five actions (paired within a repetition)

| action | extra missed instants, median (per repetition 1..5) | longest burst > 50 % missing, s | last extra miss after the question, s | streams hit | robot TTFT from the question, s (per repetition) | measured tier |
|---|---|---|---|---|---|---|
| ONE-GO | **59** (66, 74, 57, 59, 57) | **6.0** (6.5, 7.5, 5.5, 6.0, 6.0) | 6.0 | 100 % | **3.56** (4.96, 4.02, 3.29, 3.50, 3.56) | COLD in 5 of 5 |
| PIECES 2048 | **28** (28, 41, 28, 27, 27) | 1.5 (1.0, 1.5, 2.0, 1.0, 2.5) | 5.5 | 90 % | **6.10** (6.11, 6.46, 5.12, 6.10, 4.99) | cold first piece |
| PIECES 1024 | **0** (0 in all 5) | 0 | none | 0 % | **6.87** (7.34, 7.93, 6.87, 6.51, 6.67) | cold first piece |
| HOST-WARM | **0** (0 in all 5) | 0 | none | 0 % | **0.69** (0.36, 0.79, 0.76, 0.63, 0.69) | **HOST in 5 of 5** |

Tier verification, HOST-WARM in Part B: cached tokens 9,984 to 11,696 of 10,159 to 11,831 prompt tokens, and in every
repetition the server's external-KV-transfer counter rose by exactly the cached tokens over the request (local cache hits
0), so every cached token was loaded from the host tier (5 of 5 HOST; the STOP condition did not fire).

Consistency with amendment 1 (host size should not matter for cold actions, StudyENG1c Part E): ONE-GO extra misses
1.04x, robot TTFT 1.03x, burst 1.09x; P2048 1.17x, 1.03x and 1.50x; P1024 0 vs 0 misses, TTFT 1.01x. All inside 0.8x to
1.25x except the P2048 burst length, 1.5 s vs 1.0 s, which is ONE 0.5 s bin at the resolution of that measure
(per-repetition values 0.5 to 2.5 s in both amendments); not a host-size effect.

Representative Part B repetition: 4 (its ONE-GO extra-miss count, 59, is the median). Figure data:
`results/motivation/mot1/mot1_figdata_amend2.json` (Part B only, five actions, per 0.5 s bin fraction missing,
question time, each action's robot TTFT with per-repetition values, the summary table; Part A's per-run measured tier
and outcome as a separate caption block). Check plot: `results/motivation/mot1/mot1_amend2_check.png`.

### 10.4 Sanity and consistency checks (amendment 2)

| check | result |
|---|---|
| Part B NONE controls >= 99 % on time | 100 % in 5 of 5 |
| 0 HTTP errors | 0 in 30 runs |
| HOST-WARM measured HOST in Part B | 5 of 5 |
| Part A measured tier vs prediction | COLD in 5 of 5, as predicted |
| B cold actions vs amendment 1 | 1.01x to 1.17x on extra misses and robot TTFT; burst lengths explained above |

Results consistency: host-warm recall TTFT 0.36 to 0.79 s under 10 requests/s of monitoring traffic vs StudyENG1's 0.17 s
unloaded host reload and ENG1f's host-warm 0.26 / 0.34 s under P25 / P40 (2.0x to 2.7x, explained by the heavier
background and the ONE-GO body re-sending all 121 to 130 frames' bytes through the front end, which ENG1f's uuid
references did not); imposed delay of a host-warm recall 0 extra misses, consistent with ENG1f's 0.07 / 0.14 s imposed
latency; Part A's COLD outcome matches the ENG1c host-residency rule (tokens written since last use > host capacity).
No disagreement unexplained.

## 11. Amendment 3: light load (recorded 2026-11-18, BEFORE any amendment-3 run)

User request. Goal: show that the best way to serve the robot's question CHANGES with load. Amendments 1 and 2
measured a heavy-load fleet (N = 20, 10 requests/s, about 66 % of the committed 15.1 requests/s one-frame peak,
StudyD7b). This amendment measures the same scene at LIGHT load, so the figure can show a 2 x 2 (light / heavy load
x tight / roomy host).

Design (only N differs from amendments 1 and 2):

- Server: the round-1 configuration, 27 GiB host offload (tight), the same command as amendment 1 and amendment 2
  Part A, restarted at the start; host filled to 1.5x capacity at server start as before.
- Load: N = 8 dashcams, FIXED (not selected), one request per 2 s each (4 requests/s, about 26 % of the 15.1 requests/s
  peak), deadline 0.916 s server-side, the same body, frames and per-stream cache_salt as before. Stream plan:
  each repetition's amendment-1 plan (seed `mot1a1|rep{r}`, N = 20) truncated to its FIRST 8 streams, so the 8
  streams (clips, instants and phase offsets in [0, 2) s) are exactly amendments 1 and 2's first 8, and the robot
  session is the same as theirs (generating the plan with N = 8 would draw fewer offsets and select a different
  robot session).
- Robot: question at t = 20 s of a 60 s window, about 11k D2 history, the same five repetitions' sessions as
  amendments 1 and 2 (paired across amendments on the robot side).
- Actions per repetition: NONE, ONE-GO, PIECES 2048, PIECES 1024, HOST-WARM (prepared exactly as in amendment 2:
  history prefill, then fresh filler of whole p28 histories until at least 70,000 tokens, exact count recorded, then
  the window 0.5 s later). 5 repetitions, order balanced (forward in odd, reversed in even repetitions), fresh
  namespaces per run.
- Tier at the question MEASURED for every run (cached tokens and the external-KV-transfer counter delta, as in
  amendment 2); every run labelled by measured tier.
- Sanity: NONE >= 99 % on time (else INVALID, rerun once; twice INVALID in one repetition: STOP); 0 HTTP errors; cold
  actions' first request cached tokens <= 16.

Expectations (written down, not constraints; any outcome is reported):

1. ONE-GO still causes some misses at light load (requests arriving during the ~2.7 s rebuild wait behind it), but
   fewer than the 59 (median) at heavy load.
2. PIECES 1024 may serve BOTH: 0 misses and the robot under its 5 s target, because less monitoring traffic queues
   between pieces.
3. HOST-WARM prediction, tight host: writes after the history's last use by the question = filler (about 70,000 to
   81,000; amendment 2 used 80,886) + 8 streams x 0.5 requests/s x 20 s x 378 tokens (30,240) = about 100,000 to
   111,000 tokens vs the 27 GiB host capacity of 110,592. **Predicted HOST**, but at the boundary, where StudyRES1
   found the tier not reliably predictable (R3), so PARTIAL or COLD are possible and will be reported as measured.

Measures as amendments 1 and 2. Figure data: `results/motivation/mot1/mot1_figdata_amend3.json` with per action the
median and min-max of extra missed instants and robot TTFT, the measured tiers, and a `grid_2x2` block assembling
light/tight (this amendment), heavy/tight (amendment 1 cold actions plus amendment 2 Part A host-warm), heavy/roomy
(amendment 2 Part B) and light/roomy (this amendment's cold actions, borrowed because host size does not change cold
actions, StudyENG1c Part E and amendment 2's 1.01x to 1.17x check, plus this amendment's HOST-WARM only if it
measured HOST, else "not measured"), each cell stating whether it is measured directly or borrowed.

Checkout: HEAD d7acaf7 (origin had nothing newer); the working tree carries the uncommitted StudyLIVE2-harness
addendum edits under `experiments/orchestration/live2/` (asyncbackend, bridge, coordinator, procsplit,
run_live2_real, preflight), none of which this study's request path uses; their diff hash is recorded with the run.

### 11.1 Amendment 3 run record

Server: 27 GiB host (flag diff vs DE_c38 `[('38', '27')]`), restarted 12:50:09, up in 66.8 s, host filled to 189,488
tokens (1.7x the 110,592-token capacity, 7 fresh histories); 25 runs 12:53 to 13:21; server stopped 13:21. Checkout:
HEAD 6048b99 with uncommitted edits (diff sha256 5d320e6e...; this study's runner `study_mot1_dayinlife.py` plus the
StudyLIVE2-harness addendum files under `experiments/orchestration/live2/`, which this study's request path does not
import), recorded in `mot1_amend3_server.json` and `mot1_amend3_runs.json`. N = 8 (first 8 streams of amendment 1's
plans, same robot sessions: verified for all 5 repetitions before the run). HOST-WARM preparation, every repetition:
prefill 10,001 to 11,711 prompt tokens with 0 cached (cold, as intended), then 80,886 filler tokens (the same three
whole p28 histories as amendment 2), window 0.5 s after.

PROTOCOL DEVIATION (no effect on any measurement): twice during the run, host Python ran outside the request-harness
client while the server was up: a `py_compile` syntax check of `mot1_analyse.py` (12:52) and a short `python3` text
edit of `research/EXPERIMENTS.md` (about 12:53, the StudyMOT2 row). Both were CPU-only, sub-second, touched neither GPU
2 nor the server, and neither ran a request; reported as the standing rule requires.

### 11.2 Light load (N = 8), tight host (27 GiB), all five actions (paired within a repetition)

| action | extra missed instants, median (per repetition 1..5) | longest burst > 50 % missing, s | last extra miss after the question, s | streams hit | robot TTFT from the question, s (per repetition) | measured tier |
|---|---|---|---|---|---|---|
| ONE-GO | **11** (11, 14, 11, 11, 9) | 2.5 (1.5, 3.0, 2.5, 2.5, 1.0) | 2.5 | 100 % | **3.00** (3.42, 3.57, 2.85, 3.00, 2.83) | COLD in 5 of 5 |
| PIECES 2048 | **0** (0 in all 5) | 0 | none | 0 % | **3.37** (3.44, 3.67, 2.95, 3.37, 2.88) | cold first piece |
| PIECES 1024 | **0** (0 in all 5) | 0 | none | 0 % | **3.96** (3.96, 4.14, 3.52, 4.21, 3.49) | cold first piece |
| HOST-WARM | **8** (8, 8, 7, 8, 5) | 1.5 (1.5, 2.0, 1.5, 2.0, 1.0) | 2.0 | 100 % (62.5 to 100) | **2.28** (2.40, 2.63, 2.28, 2.27, 2.17) | **PARTIAL in 4, COLD in 1** |

NONE controls 240 / 240 on time in all 5 repetitions (no INVALID run); 0 HTTP errors in 25 runs; every cold action's
first request had 0 cached tokens (rule <= 16).

**Expectations vs measured.** (1) ONE-GO still causes misses at light load, fewer than heavy load: YES, 11 vs 57
(amendment 1) and 59 (amendment 2 Part B), robot 3.00 s. (2) 1,024-token pieces serve BOTH: YES, 0 extra misses in 5 of
5 and the robot at 3.49 to 4.21 s, under its 5 s target; so do 2,048-token pieces (0 misses, 2.88 to 3.67 s), which at
heavy load cost 24 misses and 5.90 s. (3) HOST-WARM predicted HOST: **NOT CONFIRMED; measured PARTIAL in 4 and COLD in
1 of 5.**

### 11.3 Tier verification and why the HOST prediction failed

| repetition | predicted | measured | cached / prompt tokens | counter delta: local / external / computed | robot TTFT, s |
|---|---|---|---|---|---|
| 1 | HOST | PARTIAL | 336 / 11,367 | 0 / 336 / 14,055 | 2.40 |
| 2 | HOST | COLD | 0 / 11,831 | 0 / 0 / 14,855 | 2.63 |
| 3 | HOST | PARTIAL | 336 / 10,160 | 0 / 336 / 12,848 | 2.28 |
| 4 | HOST | PARTIAL | 336 / 10,743 | 0 / 336 / 13,431 | 2.27 |
| 5 | HOST | PARTIAL | 336 / 10,159 | 0 / 336 / 12,469 | 2.17 |

PARTIAL here means only 336 tokens (21 blocks of 16, about 3 % of the history) came back from the host; the robot's
history was in effect cold in all five repetitions. The arithmetic the prediction rested on assumed about 70,000 filler
tokens. The pre-registered preparation (whole p28 histories, the smallest total >= 70,000, as in amendment 2) gives
80,886, so the writes after the history's last use are 80,886 + about 30,240 of monitoring before the question (8
streams x 0.5 requests/s x 20 s x 378 tokens) = about 111,126 tokens, 534 tokens MORE than the 110,592-token host. By
the ENG1c host-residency rule (tokens written since last use > host capacity means evicted) that predicts eviction,
which is what was measured; the section-11 record already gave the range "about 100,000 to 111,000" and placed the
upper end at the capacity. This is the boundary StudyRES1 R3 warned about; reported as a failed prediction, not
re-run with a smaller filler (that would be a design change). Which 21 blocks survived (probably blocks written latest
or shared with another prompt) is a candidate, NOT tested.

Why HOST-WARM's robot TTFT (2.28 s) is below ONE-GO's (3.00 s) although both recompute the history: candidate, NOT
tested: the preparation prefill sent the same images with the same multimodal uuids about 25 s earlier, so the
engine's multimodal caches may still hold their processed inputs and the question skips that part of the work; the
smaller fleet impact (8 vs 11 misses) is consistent with that shorter prefill.

### 11.4 The 2 x 2 (figure data `mot1_figdata_amend3.json`, block `grid_2x2`)

Medians over 5 repetitions: extra missed dashcam instants / robot TTFT from the question.

| cell | ONE-GO | PIECES 2048 | PIECES 1024 | HOST-WARM | serves both (0 extra misses, robot < 5 s) |
|---|---|---|---|---|---|
| light load, tight host (this amendment, measured) | 11 / 3.00 s | **0 / 3.37 s** | **0 / 3.96 s** | 8 / 2.28 s (PARTIAL or COLD) | **PIECES 2048, PIECES 1024** |
| heavy load, tight host (amendment 1 cold actions; amendment 2 Part A host-warm, measured) | 57 / 3.47 s | 24 / 5.90 s | 0 / 6.79 s | 44 / 2.62 s (COLD, cross-run misses) | **none** |
| heavy load, roomy host (amendment 2 Part B, measured) | 59 / 3.56 s | 28 / 6.10 s | 0 / 6.87 s | **0 / 0.69 s (HOST)** | **HOST-WARM** |
| light load, roomy host (cold actions BORROWED from light/tight; host-warm NOT MEASURED) | 11 / 3.00 s | **0 / 3.37 s** | **0 / 3.96 s** | not measured | **PIECES 2048, PIECES 1024** (borrowed) |

The best action changes by cell: chunked rebuilding at light load, nothing at heavy load with a tight host, keeping the
history warm in a roomy host at heavy load. Borrowing rule: host size does not change cold actions (StudyENG1c Part E;
amendment 2 Part B vs amendment 1, 1.01x to 1.17x); HOST-WARM is not borrowed into light/roomy because light/tight did
not measure HOST (0 of 5). The JSON states for every cell and action whether it is measured directly or borrowed.

### 11.5 Sanity and consistency checks (amendment 3)

| check | result |
|---|---|
| NONE controls >= 99 % on time | 100 % in 5 of 5 |
| 0 HTTP errors | 0 in 25 runs |
| cold actions' first request cached tokens <= 16 | max 0 |
| robot session and first 8 streams identical to amendments 1 and 2 | verified for 5 of 5 repetitions |
| HOST-WARM measured tier vs prediction | 0 of 5 HOST (PARTIAL 4, COLD 1): prediction failed, explained in 11.3 |

Cross-check against the committed measurements (light vs heavy, amendment 1): ONE-GO robot TTFT 3.00 vs 3.47 s (0.87x)
and P2048 / P1024 robot TTFT 0.57x / 0.58x, all faster at light load as expected (less traffic queued between pieces);
ONE-GO extra misses 0.19x (11 vs 57), scaling roughly with the request rate behind the rebuild (4 vs 10 requests/s,
0.4x) and the shorter burst (2.5 vs 5.5 s). Physical plausibility: a cold ~11k rebuild at 2.8 to 3.6 s under 4
requests/s vs the committed cold 11k recall TTFT 2.44 s (`recall_ttft_s`, unloaded): 1.2x to 1.5x, inside 2x and
slower, as a loaded engine should be. Definition audit: tiers, extra misses, burst and robot TTFT are computed by the
same code as amendments 1 and 2 (`mot1_analyse.analyse`). No disagreement unexplained.

## 12. Amendment 4: light load, roomy host, HOST-WARM only (recorded 2026-11-18, BEFORE any amendment-4 run)

User request (optional filler while waiting for StudyLIVE2's D114 build). Fills the 2 x 2's light / roomy HOST-WARM cell,
which amendment 3 left "not measured". Design: identical to amendment 3 except the host tier (256 GiB, the amendment 2
Part B server, host filled to 1.5x its capacity at server start) and the action set (HOST-WARM only, 5 repetitions,
amendment 3's first-8-stream plans and robot sessions, the same preparation: cold prefill, whole-history filler of at
least 70,000 tokens, window 0.5 s later). Prediction: **HOST in 5 of 5** (writes after the history's last use about
80,886 + 30,240 = 111,126 tokens, an order of magnitude under the 1,048,576-token host). Measures: robot TTFT from the
question, measured tier (cached tokens and the external-KV-transfer counter delta), missed instants, and extra missed
instants against amendment 3's NONE of the same repetition (a cross-run reference, not a paired difference, as in
amendment 2 Part A). Sanity: 0 HTTP errors. If StudyLIVE2's D114 commit lands mid-run, the current repetition finishes,
what is done is committed, and the remainder is recorded as not run.
