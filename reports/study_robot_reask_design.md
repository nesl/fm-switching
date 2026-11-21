# D159 (C) robot volume: the expected counts, and why the design as specified does not fix the
# power problem it was created for

Session D (flash / A6000), 2026-11-21. Analysis only, no run. CLAUDE.md Step 0: "ask what would
invalidate this run BEFORE starting it."

## The deliverable D159 (C) asked for: expected robot questions per run at 16 devices

Measured from the committed cell `v5-rules_n16_s4_1200s_h27_3t_L3_epg` (ratio 40:40:20, so 6
dashcam, 7 robot, 3 assistive devices; `run_s` 1200). Robot session spans are parsed from the
`session_id`, which encodes `start_` and `end_`. The eligible re-ask window per session runs from
its first ask to the earlier of the session end and the run horizon, which totals **6,868.2
device-seconds**.

| mean interval | expected re-asks | total robot asks | re-ask share |
|---|---|---|---|
| 15 s | 457.9 | **477.9** | 95.8 percent |
| **30 s (the default)** | **228.9** | **248.9** | **92.0 percent** |
| 60 s | 114.5 | 134.5 | 85.1 percent |
| 120 s | 57.2 | 77.2 | 74.1 percent |

Against the 20 robot asks the run produces today, the default is a **12.4x increase in asks**.
REGISTER: **CONSTRUCTED** from a measured eligible window and the declared Poisson rate, not
observed. A Poisson draw also needs the re-ask to land while the session is still playing, which
the window above already enforces.

## The blocker: asks go up 12.4x and the effective sample size does not move

The run's 20 robot asks are **20 distinct questions, each asked exactly once**. The per-session
distribution is the problem:

| distinct questions in the session | sessions |
|---|---|
| 1 | **14** |
| 2 | 3 |

D159 (C) specifies re-asks "drawing uniformly from that session's questions **already asked**". In
14 of 17 sessions that set has exactly one member, so every re-ask in those sessions is **the same
question again**. The re-ask process cannot create a distinct question, because the only questions
it is allowed to draw are ones already counted.

D159 (C) also specifies, correctly, that **CIs are clustered by question**. Clustering keys on the
distinct question, so the cluster count stays at 20 whatever the re-ask rate. Effective sample size
`n_eff = N / (1 + (m-1) rho)`:

| mean interval | asks | mean cluster size | n_eff at rho = 1.0 | at 0.8 | at 0.5 |
|---|---|---|---|---|---|
| 15 s | 477.9 | 23.89 | **20.0** | 24.7 | 38.4 |
| **30 s** | **248.9** | **12.45** | **20.0** | **24.5** | **37.0** |
| 60 s | 134.5 | 6.72 | **20.0** | 24.1 | 34.8 |
| 120 s | 77.2 | 3.86 | **20.0** | 23.5 | 31.8 |

**At any interval in the declared sweep, effective n is between 20 and 38 against the 20 we already
have.** The required n for the v5-rules robot effect was estimated at about 3,200 (CONSTRUCTED,
`reports/study_v5_rules.md`). So the design multiplies the quantity that is not binding by up to
24x and leaves the binding one unchanged. The sweep over {15, 30, 60, 120} s cannot discover this,
because every cell in it has the same 20 clusters.

`rho` is unmeasured and is the only thing that could rescue it. It will be **high**: repeated asks
of one question, same gold, same session, same device, differing only in how much history has
accumulated. Correctness on repeated asks of one question is close to a replicate, not an
independent draw. A run would measure `rho`, but betting 18 cells on it being near 0.5 is the
expensive way to find out, and `rho` near 0.5 still only buys n_eff 37.

## A second, independent problem: 92 percent of asks would carry a stale device answer

A re-ask is answered against **more history** than the original, which is its purpose. But the
device answer comes from the committed D87 table keyed on `question_id`
(`fleet/trace.py:753-759`), so a re-ask reuses the device answer measured at the **original**,
shorter history, while `device_latency_s` IS recomputed from the new `history_tokens`.

So the harness already models the device as **holding history that grows** (its latency grows with
`hist_tok`), while its **accuracy** is frozen. If the device holds growing history, its real answer
should improve with it, so freezing understates the device and therefore **overstates the benefit of
escalating**. That is the direction that favours the hypothesis, which is the direction check 6
forbids for a headline: "if the proxy is known to be questionable, it may not be used for a
headline conclusion."

This matters more here than it would elsewhere because of a finding from last night: **16 of the 20
extra escalations v5-rules made resolved to the device answer anyway**. Arms reach the device answer
often, so the staleness enters the arm-versus-arm comparison and not only the device-only baseline.
At the 30 s default it would enter on 92 percent of robot asks.

## What I propose instead, and it moves the binding axis

The binding constraint is **distinct questions**, and there is a reservoir of them already in the
trace that the generator currently drops. `fleet/trace.py:742-748` skips a question when
`q.t_ask > sm.duration_s`, when `t_run > run_s`, and when `q.t_ask < join` (counted as
`robot_questions_before_join`). The first two are **recoverable by exactly the mechanism D159 (C)
introduces**: ask them later, inside the session, on a history that is a superset of what they
needed, with gold unchanged. The third is not recoverable, because the cloud never received the
history those questions depend on.

So the same Poisson machinery, pointed at a different draw pool:

- **draw first from the session's questions not yet asked whose original ask time has passed**,
  which are new clusters;
- fall back to an already-asked question only when that set is empty, which is the D159 (C)
  behaviour and keeps the volume;
- the device-answer problem is **the same** for a first ask of a dropped question as for a re-ask,
  so it does not go away, but a first ask at least adds a cluster for the cost.

I have not measured how many questions this recovers, and I will not guess: the code comment at
`fleet/trace.py:318-321` says the LH-REQ pool is 69 questions against the 20 asked, which suggests
the reservoir is real, but `robot_questions_before_join` is not separated from the other two skip
reasons in any committed artefact. **Separating those three counters is a one-cell, no-GPU
measurement and it is the next thing I would run.**

## What I am doing and not doing

**Not posting `RQ30_ARGS` yet.** Posting it starts 18 cells, about 6 GPU-hours, on a metric whose
effective sample size is 20 to 38 either way and whose device baseline is stale on 92 percent of its
rows. Step 0 exists for this: a minute spent before against a sweep re-done after.

**Building regardless**, because every variant needs it: the re-ask trace transform with the
identical-across-arms digest proof, D84 isolation unchanged, and beyond-32k asks counted and never
truncated. That work is not wasted by either ruling.

**Three questions for the user**, each with my default if no answer comes:

1. **Draw pool.** Default: the amended pool above (unasked-with-passed-ask-time first, already-asked
   as fallback), because it is a strict superset of D159 (C)'s behaviour and the only version that
   can raise the cluster count. Reverting to already-asked-only is one flag.
2. **The device answer on a re-ask.** Default: freeze it, label the re-ask subset
   **unvalidated for any headline** per check 6, and report originals and re-asks separately so the
   20 clean clusters are never diluted by the 229 stale ones. The fix is a device re-record at
   re-ask histories, which is Orin work and which the EP-G dashcam re-record already queues behind.
3. **Whether volume is the right lever at all.** If the aim is power on the robot claim, distinct
   questions is the axis, and the levers that move it are more robot sessions played (more devices
   or shorter plays) and the dropped-question reservoir. Re-asks mainly buy a within-question
   history-growth curve, which is interesting in itself (does the same question flip from wrong to
   right as evidence arrives?) but is a different experiment from the one D159 (C) is framed as.

## Register

- Expected counts: **CONSTRUCTED** from a **MEASURED** eligible window (6,868.2 device-seconds) and
  the declared rate.
- 20 asks, 20 distinct questions, 14 of 17 sessions single-question: **MEASURED** from
  `outcomes.jsonl` of a committed cell.
- `n_eff`: **CONSTRUCTED**, and `rho` is **UNMEASURED**. The cluster count of 20 is measured and is
  what drives the conclusion; it holds at every `rho`.
- The device-answer bias **direction** is **ARGUED**, not measured, from the harness modelling
  device latency as growing with history while holding accuracy fixed.

---

## MEASURED 08:00: my own proposal recovers ZERO questions, and the pool caps distinct n at 69

The count_only measurement is run (on flash, CPU only; the H100 correctly declined it as host
Python during live runs). It reproduces the committed cell exactly, which is the control on the
measurement: 20 robot asks, 20 distinct, pool coverage 0.2899.

| generator stat, seed 4, n16, ratio 40:40:20, `lh_req` | value |
|---|---|
| `robot_question_pool_n` | **69** |
| `robot_session_pool_n` | **51** |
| `robot_sessions_started` | 22 |
| `robot_sessions_completed` | 15 |
| `robot_questions_total` | **20** |
| `robot_distinct_questions_asked` | **20** |
| `robot_asks_per_distinct_question` | 1.0 |
| `robot_questions_before_join` | **0** |

Classifying all 69 pool questions by what happened to them:

| | questions | recoverable by asking later? |
|---|---|---|
| asked | **20** | n/a |
| skipped, `t_ask` beyond the played session duration | **0** | n/a, none exist |
| skipped, absolute time beyond the 1,200 s run horizon | **8** | **NO** |
| in a session that was never played at all | **41** | **NO** |
| dropped before the join point | **0** | n/a, none exist |

**My proposed amendment recovers nothing, and I withdraw it.** I argued that the generator's two
horizon skips were "recoverable by exactly the mechanism D159 (C) introduces: ask them later." Both
halves of that are wrong on measurement:

- The **beyond-session** bucket, which is the one that would have been recoverable, is **empty**.
- The **beyond-run** 8 are skipped precisely because there is **no later time inside the run**.
  Asking them would mean asking *earlier* than their original time, which is the one thing the gold
  validity argument forbids.
- The **41** are in sessions never played. No question-level mechanism reaches them; only playing
  more sessions does.

I inferred a reservoir from a stale code comment (`fleet/trace.py:318-321` says "the LH-REQ pool at
69 questions", which is right) plus an assumption about which skip dominated, and did not measure
the split before proposing the fix. Same failure shape as the knee bracket and the race audit: an
inference standing in for a measurement.

### What the measurement says the real lever is, and where it runs out

Distinct questions are limited by **sessions played**: 22 of 51, carrying 28 of the 69 questions.
The levers that move it are more robot device-seconds (more robot devices, a ratio shifted toward
robot, or a longer run), not anything done per question. **And the pool is a hard ceiling: 69.**

Against a required n of about 3,200 (CONSTRUCTED, `reports/study_v5_rules.md`), playing every
session in the pool gives at most **69 distinct robot questions, a 3.45x improvement that falls
short by a factor of about 46.** So **no lever inside this dataset reaches the required n**, and
proposing a new dataset is forbidden by CLAUDE.md's rules. That is the honest answer to D159 (C)'s
third question, and it is an answer about the experiment's design rather than about its
implementation.

### Where that leaves re-asks, which now look useful for a different reason

The required n of 3,200 was constructed for an **unpaired** comparison of proportions. Re-asks do
not give independent samples, but they do give something a between-question design cannot: the
**same question, in the same session, asked repeatedly against a monotonically growing history**,
identically for every arm. That is a **repeated-measures design**, in which each question is its own
control and the arm contrast is estimated within question. Power then comes from pairing rather
than from independence, and the 12.4x asks are spent on the paired structure instead of being
discarded by the clustering.

It also measures something directly relevant to the project's own claim: **does an answer flip from
wrong to right as evidence accumulates, and does the arm that warms get there sooner?** That is
closer to Context Inertia than a one-shot accuracy difference is.

So my recommendation changes. **Keep D159 (C)'s mechanism exactly as the user specified it**,
including drawing from already-asked questions in the same session, which I had proposed to amend
and no longer do. Change the **analysis** from "more samples" to "repeated measures within
question", and report the history-growth curve per question rather than a pooled proportion. The
device-answer staleness objection from the section above is **unchanged and still binding**, and it
bites harder in a repeated-measures design, because the within-question contrast is exactly where a
frozen device answer sits on one side of the comparison.

---

## MEASURED 11:15: the Orin's REASK record lands, and it REFUTES my directional claim

`experiments/orchestration/live2/v5/reask_device_join.py`, joining StudyORIN-REC-REASK seeds 4 to 7
over the frozen D87 answers on `opportunity_id`. All four seeds are pushed; the join writes one
replacement row per re-ask.

| seed | re-asks | differs from frozen | measured device accuracy | frozen | delta |
|---|---|---|---|---|---|
| 4 | 112 | 38 (**33.9 percent**) | 0.152 | 0.196 | **-0.045** |
| 5 | 102 | 27 (26.5 percent) | 0.225 | 0.157 | **+0.069** |
| 6 | 101 | 46 (**45.5 percent**) | 0.109 | 0.218 | **-0.109** |
| 7 | 83 | 30 (36.1 percent) | 0.217 | 0.169 | **+0.048** |
| **pooled** | **398** | 141 (35.4 percent) | **0.1734** | **0.1859** | **-0.0126** |

My seed-4 figure of 33.9 percent reproduces the Orin's independently reported 34 percent.

### What I got wrong

I argued, twice, that freezing the device answer **understates the device and therefore overstates
the benefit of escalating**, and I reasoned it from the harness modelling device latency as growing
with history while holding accuracy fixed. **That direction is not supported.** It goes both ways:
frozen **overstated** the device at seeds 4 and 6, and **understated** it at seeds 5 and 7. At seed
6 it overstated by a factor of two, 0.218 against a measured 0.109.

The argument was plausible and it was not measured. The honest statement is that the frozen answer
is **wrong on about a third of re-asks in an unpredictable direction**, which is worse for an
arm comparison than a known bias would be: a known direction can be bounded, a sign that flips by
seed cannot.

### The pooled number would have hidden it, which is check 3

Pooled, the frozen and measured device accuracies differ by **-1.26 pp**, which reads as "freezing
barely matters". Per seed the swings are **-10.9 to +6.9 pp**, eight times larger and in both
directions. A pooled headline would have concluded the opposite of the truth. This is the
"real effect averaged into undetectability" shape, with the extra twist that the strata cancel
rather than dilute.

It bites hardest in exactly the analysis D161 (2) ordered. A **paired, within-question** contrast
puts the device answer on one side of the comparison, so a per-seed sign flip is not noise that
averages out across seeds, it is a different comparator in each seed's pairing.

### Parity, the control on the measurement

| seed | reproduces part 1 | reproduces WARM |
|---|---|---|
| 4 | 19 of 20 | 20 of 20 |
| 5 | 22 of 22 | 22 of 22 |
| 6 | 16 of 17 | 17 of 17 |
| 7 | 18 of 19 | 19 of 19 |

**WARM is reproduced in 78 of 78**, and the three part-1 misses are the declared D81 prefix-cache
near-tie drift. So the measurement apparatus is sound and the differences above are real
re-ask-time behaviour, not a recording artefact.

### Latency, and a cross-check worth keeping

`device_latency_s` is replaced by the Orin's measured `completion_s`, not `ttft_s`, because D155
scores a device answer by **when it arrives** and the committed warm table is completion-based
(`ORIN_REC_WARM_COMPLETION_P50` 0.2697, table span 0.2503 to 0.3108). Cross-check on the first
joined row: measured `completion_s` **0.2954** against the committed warm reference **0.2944** for
the same question, agreeing to about 1 ms. That is an independent confirmation that the committed
table is completion-based and that D161 (3)'s latency requirement was already met.

### Consequence for the PROVISIONAL label

The label can be removed per seed as its join lands, which is now all four. But the removal is only
honest alongside the finding above: **the robot numbers on re-asks moved by up to 11 pp per seed and
in both directions**, so any rq30 cell scored before this join is not merely provisional, it is
scored against a comparator that was wrong on a third of its rows.
