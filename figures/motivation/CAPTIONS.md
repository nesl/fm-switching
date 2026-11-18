# StudyFIG1-motivation: draft captions (M1-M6)

Takeaway first, then the setup, then n and the error-bar definition. Plain words,
no em dashes. Every number here is cross-checked against its source report in the
per-figure JSON. Caching conditions are stated wherever a latency is shown.

## M1 (figM1_cloud_value)
The cloud tier earns its keep where the device's recent window has dropped the
evidence. (a) On S-EMBER recall, a 32B cloud model reading the full history beats a
4B device model reading only its last 120 s by +21.7 pp when the answer's evidence
is older than the window, and by only +4.8 pp when the evidence is still inside it.
(b) On the dashcam monitoring task the cloud also captures +0.090 challenge mAP over
device-only. Panel (a): n = 97 questions (evidence outside) and 748 (inside); bars
are accuracy with 95 percent bootstrap confidence intervals (2,000 resamples,
resampling questions). Panel (b): challenge mAP over 300 clips, every clip held out,
95 percent CI over 2,000 paired clip resamples. These are accuracy and ranking
numbers, not latencies, so no caching condition applies.

## M2 (figM2_interference)
One cold 11,000-token rebuild dropped into a loaded server turns millisecond replies
into multi-second ones for everything that arrives while it runs. Each point is a
background request in one paired run at load P40: grey without the rebuild, orange
with it, plotted against when it arrived in the trace; the shaded band is the
rebuild's engine span. Requests arriving during and just after the rebuild wait
seconds and the queue drains only over the next few seconds. n = 65 background
requests in the pair; the pair is the one whose total imposed delay (44.9 s) is the
median of the cell's 15 fit pairs. Caching: prefix caching on, but the rebuild and
the background requests are cold (per-run uuid namespaces, zero cached-token
mismatches between the two arms).

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
coloured by what it served: the rebuild or its piece, background requests, or both;
top is a one-go rebuild, bottom a 1,024-piece chain. The annotated inter-piece gap is
158 ms (cell median 0.173 s), and the engine serves background in it. One
representative trial per action (mode A, load P40), the trial whose imposed delay is
closest to the cell median. Caching: prefix caching on; the add-on that logged the
steps failed the unloaded overhead gate and passed at P40, and both arms ran with it,
so the comparison is unaffected.

## M4 (figM4_tiers)
A warm restore from host or disk is far cheaper than a cold rebuild and imposes almost
nothing on other requests, but several disk restores at once serialize on disk
bandwidth. (a) Restoring an 11k history costs 2.69 s cold, 0.20 s from host and 1.15 s
from disk. (b) At load P40 a cold rebuild imposes 36.5 s on others against about 0.1 s
for host or disk. (c) One, two or four simultaneous disk loads take 1.12 / 1.86 /
3.53 s each, and four at once exceed one solo cold recompute (dashed). n = 20 solo
repetitions per state (a), 15 fit pairs per state (b), 10 repetitions per level (c);
whiskers are p10 to p90 in (a) and (c) and the committed 95 percent CI in (b).
Caching: cold sends image bytes with no KV anywhere; host and disk restore prewritten
KV; page-cache residency for the disk tier is verified empty (fincore, O_DIRECT).

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
