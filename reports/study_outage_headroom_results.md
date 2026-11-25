# StudyOUTAGE-HEADROOM — results (PRELIMINARY)

Computed 2026-11-24 on Orin, offline from the committed s4 trace and committed constants, CPU,
read-only, NO PLOT. Formulation and the upper-bound argument: `reports/study_outage_headroom.md`
(committed `cd8f6eb7`). Values: `reports/figures/outage_headroom_results.json`.

Trace fairness digest re-asserted = `96c1a0b4...` (MATCH). Positive control (zero-length outage)
gives empty backlog and zero headroom. No STOP-gate flag fired (no headroom exceeds its in-window
decision count; no window negative). This is a necessary-condition (headroom) study: it bounds the
MOST an ideal recovery order could save over FIFO; it is NOT an achieved policy result.

## Setup
s4, 1x. Composition read from the trace: 6 dashcam, 7 robot, 3 single-shot (16 devices). Outage
lengths {10, 30, 60} s x offline sets {1 robot, 1 dashcam, K=2, K=4, K=7 correlated} x 5 starts
(200/400/600/800/1000 s). Backlog = frames captured during the outage (uploaded at reconnect) plus
the cold re-prefill of the next decision per offline device (KV lost on disconnect). Uplinks are
PER-DEVICE (parallel); the cloud GPU is SHARED (serial). Recovery window R(pipelined) =
max(max-device upload, summed GPU rebuild); R(serial) = their sum (looser). Window on the committed
13.6 Mbit/s link (D75); a provisional 0.9 Mbit/s low tier (StudyNET-TIER1 hand-injected value)
reported beside it, PROVISIONAL until the Ookla tiers land.

## Headline answer
**Yes, but modestly, and only on dashcam-heavy or correlated outages at the committed link.** At
13.6 Mbit/s the reconnect burst clears in roughly **0.6-3.8 s** (pipelined); no scenario reaches the
>10 s LARGE bucket. The order of recovery can change on-time answers in the 1-4 s window of
dashcam-involving and correlated scenarios at 30-60 s (and K4/K7 even at 10 s); it cannot in short
(10 s) small outages or in ANY robot-only outage (those clear under 1 s: NO ROOM). The separable
headroom is SMALL: a handful of dashcam episodes and 0-2 recall/single-shot questions per scenario.

## Recovery window and verdict, committed 13.6 Mbit/s link (pipelined R, mean over 5 starts)

| outage | offline set | buffered frames | cold tokens | max upload s | GPU rebuild s | R pipelined s | verdict | headroom fit (dash/robot/ss) |
|---|---|---|---|---|---|---|---|---|
| 10 s | robot1 | 5 | 12,093 | 0.12 | 0.67 | 0.67 | NO ROOM | 5 / 0 / 0 |
| 10 s | dashcam1 | 14 | 2,004 | 0.58 | 0.11 | 0.58 | NO ROOM | 5 / 0 / 0 |
| 10 s | K2 | 19 | 14,097 | 0.58 | 0.79 | 0.81 | NO ROOM | 5 / 0 / 0 |
| 10 s | K4 | 25 | 33,214 | 0.58 | 1.85 | 1.85 | SOME ROOM | 6 / 0 / 1 |
| 10 s | K7 | 47 | 52,934 | 0.70 | 2.95 | 2.95 | SOME ROOM | 6 / 0 / 1 |
| 30 s | robot1 | 15 | 12,741 | 0.26 | 0.71 | 0.71 | NO ROOM | 5 / 0 / 0 |
| 30 s | dashcam1 | 49 | 4,438 | 1.84 | 0.25 | 1.84 | SOME ROOM | 6 / 1 / 1 |
| 30 s | K2 | 64 | 17,179 | 1.84 | 0.96 | 1.84 | SOME ROOM | 6 / 1 / 1 |
| 30 s | K4 | 82 | 36,600 | 1.84 | 2.04 | 2.17 | SOME ROOM | 6 / 1 / 1 |
| 30 s | K7 | 148 | 57,575 | 1.88 | 3.21 | 3.21 | SOME ROOM | 6 / 1 / 1 |
| 60 s | robot1 | 30 | 13,137 | 0.48 | 0.73 | 0.74 | NO ROOM | 6 / 0 / 0 |
| 60 s | dashcam1 | 99 | 4,100 | 3.71 | 0.23 | 3.71 | SOME ROOM | 8 / 0 / 2 |
| 60 s | K2 | 129 | 17,237 | 3.71 | 0.96 | 3.71 | SOME ROOM | 8 / 0 / 2 |
| 60 s | K4 | 165 | 28,337 | 3.71 | 1.58 | 3.71 | SOME ROOM | 8 / 0 / 2 |
| 60 s | K7 | 300 | 49,102 | 3.78 | 2.74 | 3.78 | SOME ROOM | 8 / 0 / 2 |

(headroom fit = in-window decisions, in D192 units, that would be served on time if PRIORITIZED at
rate T and that FIFO would delay behind the backlog; it is the upper bound on what recovery ORDER
can save. The raw in-window ceiling equals these for dashcam and is within 0-1 of them elsewhere.)

## What binds the window
- **Dashcam uploads bind, not the GPU.** A dashcam adds one 62.7 KB frame every 0.5 s (2 fps). Its
  buffered video is the upload bottleneck: 1 dashcam offline 60 s = 99 frames = 3.71 s to upload at
  13.6 Mbit/s, while its cold episode re-prefill is only ~4,100 tokens = 0.23 s on the GPU.
- **Correlation loads the GPU, not the uplink.** Uplinks are per-device and parallel, so K devices
  offline together do NOT lengthen the upload chain (max over devices ~ one device). They lengthen
  the SHARED GPU cold-rebuild, which sums: K7/10 s = 2.95 s of GPU. The shared GPU is the only
  resource that couples simultaneously-reconnecting devices.
- **Robot-only outages have no room.** Robot questions are sparse (median 29 s apart, 20 per device
  over the run), the buffered upload is small, and a single cold history rebuild (~12-13 k tokens)
  is ~0.7 s. Neither resource crosses 1 s, so recovery order cannot change a robot answer here.
- **The headroom is dashcam-dominated** because dashcam decisions are dense (2 instants/s x 6
  devices): a 1-4 s window catches 5-8 episodes whose 1.0 s deadlines FIFO would blow by replaying
  stale backlog first. Recall and single-shot decisions are too sparse to be caught in so short a
  window (0-2 per scenario), so they contribute little separable headroom.

## Low tier 0.9 Mbit/s (PROVISIONAL) and a physical-plausibility flag
At 0.9 Mbit/s the window is upload-bound and balloons: dashcam1 at 30 s -> 27 s, at 60 s -> 55 s;
K7/10 s -> 10.0 s; most 30-60 s scenarios reach LARGE (>10 s), with headroom growing to 19-39
dashcam episodes.

**But this tier is below the dashcam's own steady-state upload need and the low-tier numbers are
confounded (flagged, consistency check 2):** a dashcam produces 2 fps x 62,670 B = 125,340 B/s =
1.003 Mbit/s of video; 0.9 Mbit/s delivers 112,500 B/s = 0.90x of that, so a dashcam at 0.9 Mbit/s
is chronically backlogged EVEN WHEN ONLINE, independent of any outage. The low-tier "recovery
window" therefore mixes the reconnect burst with chronic under-provisioning and must not be read as
a pure outage effect. It is reported for shape only and is PROVISIONAL until the Ookla tiers land;
at the real cited tiers (if above ~1.0 Mbit/s for dashcam) the default-link reading governs.

## Verdict per bucket (committed link)
- NO ROOM (<1 s): all robot-only outages; 10 s dashcam1; 10 s K2.
- SOME ROOM (1-10 s): 10 s K4/K7; all 30 s and 60 s dashcam-involving and correlated sets.
- LARGE ROOM (>10 s): none at 13.6 Mbit/s.

## Conclusion
On the committed s4 trace at the committed link, an outage **can** separate policies, but the
separable prize is small (single-digit dashcam episodes) and exists only for dashcam-heavy or
correlated outages of 30 s or more; robot-only outages cannot separate policies at all. The regime
is upload-bound per dashcam and GPU-bound across correlated devices. Whether the prize is worth a
policy distinction depends on the real poor-tier uplink: if it sits near or below the dashcam's
~1.0 Mbit/s sustained need, the system is upload-starved for a different reason than recovery order,
and that confound must be resolved (Ookla tiers) before an outage study is run as a policy
comparison. This preliminary bound says WHERE to look (dashcam, correlated, >=30 s) and warns that
the low-tier shape is dominated by chronic under-provisioning, not ordering.

## Consistency checks
1. Cross-check: per-frame bytes (nexar q90 62,670 B; sember d2 24,487 B) and T(1x)=17,945.2 tok/s
   are the committed values; EPG token law 42+338 n matches the trace's prompt tokens exactly.
2. Physical plausibility: FLAGGED — the 0.9 Mbit/s tier is 0.90x the dashcam's sustained upload
   need; low-tier windows are confounded and marked provisional. Default-tier rates are 13.6x
   headroom, physically consistent.
3. Distribution: windows reported per scenario (5 starts); the table shows means, the JSON every
   start. No constant-where-distribution-expected (windows vary with start and set).
4. Definition audit: D192 units (dashcam EPISODE, recall/single-shot QUESTION); deadlines L_dash
   1.0 / L_rob 3.0 / L_ss 2.0; "headroom" defined as the ideal-minus-FIFO upper bound, not an
   achieved value, and marked as such.
5. Claim linkage: bears on FORMULATION.md Context Inertia (transfer+reconstruction) and on whether a
   transient-capacity regime separates policies. A mostly SOME/NO-ROOM result at the committed link
   WEAKENS the case that outages are a strong discriminating regime; it identifies the dashcam
   correlated >=30 s corner as the only place to look.
6. Proxy validity: the recovery window is a MODEL (committed link + D162 + token law), not a
   measurement; it is a planning bound, stated as such, and the low-tier confound is named.
7. Positive control: D=0 gives empty backlog, R=0, headroom 0 (passed).
