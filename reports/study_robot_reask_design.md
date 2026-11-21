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
