# StudyMOT1-dayinlife: one robot rebuild in a monitored dashcam fleet (motivation, claim 6)

Status: first design **STOPPED AT N SELECTION (2026-11-18 09:20)**; AMENDED by the user the same morning (section 0) and rerun. The pre-registered rule (largest N in {8, 16, 24, 32} whose
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

## 5. Files

New: `experiments/motivation/study_mot1_dayinlife.py`, `experiments/motivation/mot1_analyse.py` (written for the main
runs, not run), `reports/study_mot1_dayinlife.md`, `results/motivation/mot1/` (`mot1_requests.jsonl.gz`,
`mot1_runs.json`, `mot1_server.json`, `mot1.log`). Changed: `research/EXPERIMENTS.md`, `results/INDEX.md`,
`research/STATUS.md`.
