# StudyFIG1-motivation: draft captions (M1-M6)

Takeaway first, then the setup, then n and the error-bar definition. Plain words,
no em dashes. Every number here is cross-checked against its source report in the
per-figure JSON. Caching conditions are stated wherever a latency is shown.

Palette (Okabe-Ito, colour-blind-safe; the same colour means the same thing across
figures, and each series also carries a distinct marker or hatch): cold / one go =
vermillion #D55E00; host-warm = bluish green #009E73 (the host tier's colour); GPU-warm
= orange #E69F00; 2,048-token pieces = sky blue #56B4E9; 1,024-token pieces = dark blue
#0072B2.

## M1 (figM1_cloud_value)
The cloud tier earns its keep where the device's recent window has dropped the
evidence. (a) On S-EMBER recall, device versus cloud (a bigger model plus the full
history): a 32B cloud model reading the full history beats a 4B device model reading
only its last 120 s by +21.7 pp when the answer's evidence is older than the window,
and by only +4.8 pp when the evidence is still inside it. History alone accounts for
most of this: holding the model fixed at 32B, the full history beats the recent window
by +17.5 pp on the same outside-window questions (StudyR1 K1 minus K3). (b) On the
dashcam monitoring task the cloud also captures +0.090 challenge mAP over device-only.
Panel (a): n = 97 questions (evidence outside) and 748 (inside); bars are accuracy with
95 percent bootstrap confidence intervals (2,000 resamples, resampling questions).
Panel (b): challenge mAP over 300 clips, every clip held out, 95 percent CI over 2,000
paired clip resamples. These are accuracy and ranking numbers, not latencies, so no
caching condition applies.

## M2 (figM2_interference)
One cold 11,000-token rebuild dropped into a loaded server turns millisecond replies
into multi-second ones for everything that arrives while it runs. Each point is a
background request in one paired run at load P40: grey without the rebuild, orange
with it, plotted against when it arrived in the trace; the shaded band is the
rebuild's engine span. Requests arriving during and just after the rebuild wait
seconds and the queue drains only over the next few seconds. n = 65 background
requests in the pair; the pair is the one whose total imposed delay (44.9 s) is the
median of the cell's 15 fit pairs. This 44.9 s (StudyENG1d, P40) and the 36.5 s cold
value in M4 (StudyENG1c Part D, also P40) come from different studies with different
background traces, so they are the same quantity measured twice, not one number. Caching:
prefix caching on, but the rebuild and the background requests are cold (per-run uuid
namespaces, zero cached-token mismatches between the two arms).

## M3a (figM3a_shape)
Rebuilding a cold history as small pieces instead of one request cuts the delay it
imposes on others about fourfold, for roughly one extra second of the job's own
first-token latency. Each point is one rebuild shape: one go, 2,048-token pieces, or
1,024-token pieces; x is the job's own TTFT and y (log) is the total delay imposed on
other requests. n = 65 / 72 / 70 cold-tier trials on the host-full (capped) servers;
markers are medians with 95 percent bootstrap confidence intervals of the median in
both directions (2,000 resamples, resampling trials). Caching: prefix caching on, host
tier full, every cold arrival a fresh rebuild.

## M3b (figM3b_pieces)
A one-go rebuild holds the engine in one long span, while a chained rebuild runs each
piece in a single step and leaves real gaps between pieces in which the engine serves
queued background requests. Each block is one engine step over a common 4 s window,
coloured by what it served: the rebuild or its piece, background requests, both, or
idle (white); top is a one-go rebuild, bottom a 1,024-piece chain. The one-go row's
first blank stretch is the engine sitting idle while the action's 22.7 MB body is
preprocessed on the front end; after its long prefill block the steps turn pink because
the rest of the rebuild is still decoding alongside background requests the engine has
now admitted. The annotated inter-piece gap is 158 ms (cell median 0.173 s), and the
engine serves background in it. One representative trial per action (mode A, load P40),
the trial whose imposed delay is closest to the cell median. Caching: prefix caching on;
the add-on that logged the steps failed the unloaded overhead gate and passed at P40,
and both arms ran with it, so the comparison is unaffected.

## M4 (figM4_tiers)
The faster a tier serves a held history, the cheaper it is for everyone, but the faster
tiers hold only a handful of histories. The three tiers are GPU-warm, host and cold;
disk is not a tier yet (design log D78, open question Q12) and is not shown. (a)
Restoring an 11,184-token history costs 0.10 s GPU-warm, 0.17 s from host and 2.74 s
cold (all StudyENG1 Part D, concurrency 1). (b) Under a background load the GPU-warm and
host restores impose about 0 s on other requests while a cold rebuild imposes about 14 s
(StudyENG1c Part D, by tier at arrival; all three tiers measured under one load). (c)
But the GPU pool holds only about 5 such histories and the host about 4 (at 27 GiB) to
88 (at 256 GiB) beyond the GPU pool, while cold is unbounded. n = 30 probes per tier
(a), 11 / 11 / 65 trials per tier (b), capacity arithmetic in the JSON (c); whiskers are
p10 to p90 in (a) and the 95 percent bootstrap CI of the median in (b). Caching: cold
sends image bytes with no KV; host restores KV from the host tier; GPU-warm is KV
resident on the GPU.

## M5 (figM5_predictability)
The cost model tracks the measured delay a rebuild imposes on others and ranks the
actions correctly, but it systematically over-predicts the delay of chained piece
rebuilds. Predicted (x) versus measured (y) delay, log-log, with the y = x line;
points are the 180 held-back one-shot pairs (120 StudyENG1c Part D, 60 StudyENG1d),
coloured by action. Action ranking agreement is 19 of 20 included pairs (StudyENG1c)
and 12 of 12 (StudyENG1d), and chained pieces are over-predicted 1.5x (2,048-token)
to 1.9x (1,024-token). Caching: this is a CPU-only replay of a frozen cost model
against committed H100 measurements, so no inference or caching enters the scoring;
warm and near-zero delays are clamped to the log-axis floor.

## M6 (figM6_workload)
On the real robot workload a held history is routinely ten to thirty thousand tokens
by the time a question is asked, so a cold rebuild of it costs several seconds, which
is what keeping it warm avoids. The curve is the CDF over questions of the D2 history
size in tokens, played from the start of each session; the dotted line is the median
(10,584 tokens) and the two dashed lines mark 11k and 28k with the committed cold
rebuild time at each (2.7 s and 7.6 s). n = 839 answered questions. Caching: the token
counts are input sizes with no latency; the cold-rebuild anchors are prefix-caching-off
cold recompute measurements on the 32B serving stack.

## M7 (figM7_dayinlife)
Only a warm history answers the robot on time and leaves the fleet unharmed: a cold
history answered in one go harms the fleet, and cutting it into pieces only trades that
harm for a robot that misses its own deadline, so one point in a thousand lands in the
good corner. The setting is 20 dashcams monitored on the cloud at one request every two
seconds (66 percent of the 32B one-frame peak) when a single robot question arrives
needing its ~11k-token history, on a roomy 256 GiB host, over 5 paired repetitions; each
point is one action at the median robot answer time from the question (x) and the median
extra dashcam deadlines missed over the no-question control (y), and only host-warm, at
0.69 s and 0 extra misses, sits in the shaded good region (robot under its 5 s deadline,
dashed, D71, and the fleet unharmed), whereas one go is on time but adds 59 misses, and
the 2,048- and 1,024-token pieces spare more of the fleet (28 and 0) only by answering
late (6.10 s and 6.87 s). With a tight 27 GiB host the warmed history had instead been
flushed by question time in 5 of 5 runs and cost the fleet what a cold one-go rebuild
costs. Caching: prefix caching on; one go and the pieces rebuild the ~11k history from
cold, while host-warm is a host reload (measured on the host tier in 5 of 5 Part B runs);
the dashcams run the live one-request-per-two-seconds cloud service share. n = 20 dashcams
over 5 repetitions; the whiskers are the minimum to maximum across the repetitions in
both directions.

## M7b (figM7b_grid)
A robot's roughly 11k-token history question arrives at t = 20 s while each dashcam sends one monitoring request every 2 s, and the panels ask which way of serving that question is best as the fleet load (rows: light 8 dashcams, heavy 20) and the host memory (columns: tight 27 GiB, roomy 256 GiB) change, so that no fixed rule wins everywhere. Each point is one action at its median robot answer time from the question (x) and its median extra dashcam deadlines missed over the no-question control (y), with min-to-max whiskers; the dashed line is the robot's 5 s deadline and the shaded band is the good region (robot on time and fleet unharmed). At light load with a tight host the pieces give 0 extra misses and the robot answers at 3.4 s (2,048-token pieces) or 4.0 s (1,024-token pieces), so pieces serve both. At heavy load with a tight host one go costs 57 extra misses, the 1,024-token pieces answer late at 6.8 s, and the host-warm history had been flushed, so nothing serves both. At heavy load with a roomy host the warm history gives 0 extra misses and answers in 0.69 s, so only a warm history serves both. A hollow host-warm marker means the history had been evicted by question time, so it answered cold in practice. The light/roomy cold actions are borrowed from light/tight because host size does not change a cold action (StudyENG1c Part E; amendment 2 and amendment 1 agree within 1.01 to 1.17x), and light/roomy host-warm was not measured. n = 5 paired repetitions per cell; whiskers are min to max.
