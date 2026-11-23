# StudyRUNG4: the counterfactual rung on the rung-3 base — PRE-REGISTRATION

D190 (3), D191 items 0 to 2. Written and **committed before any cell of this rung is posted**, which
is what D190 (3) requires. Every bar below was **supplied by the user** and is recorded verbatim;
none of it is recomputed here, and nothing in it may be moved after a cell runs.

Arm family: `experiments/orchestration/live2/arms_v6cfr3.py`. Names are recorded in
`research/arm_name_map.md`.

---

## 1. What rung 4 is

**The ladder is CUMULATIVE.** Rung 4 is rung 3 plus the counterfactual decisions, not rung 2 plus
them.

| rung | arm | what it adds |
|---|---|---|
| 2 | `covex-v6-state-uo-c5attr` | the C5 attribution rule |
| 3 | `covex-v6-fair-c5attr` | the D178 (2) deficit feed; on this base the ORDERING consumer is the whole of it |
| 4 | `covex-v6-cf-c5attr` | **two** counterfactual decisions of spec v6 section 7 |

The two decisions, reported separately throughout:

* **protect-and-defer** (`cf_protect_defer`, D165 (D)) — when an alert episode is active and a
  recall **rebuild or warm** is large and not urgent, protect the victim history and defer or chunk
  the rebuild to its latest safe start if its predicted harm exceeds the margin.
* **question-deferral** (`cf_request_defer`, D151 (3), scoped into rung 4 by **D191 item 2**) —
  defer a recall **question** to its latest safe start when an alert episode is active and the
  deferral's predicted harm saving exceeds the margin.

Why both: see section 2. `covex-v6-cf-pd-c5attr` (another family) is protect-and-defer over a
**rung-2** base, where the deficit weight is the constant 1.0 by that family's own record. This rung
is a different arm and a different question.

## 2. Why the second decision is in rung 4 at all, and why that is a scope ruling and not a tuning

Measured here, dry, seed 4, 16 devices, posted knobs, **1x memory**, on the rung-3 base:
protect-and-defer moved **zero** decisions and **not one** of its decisions reached the harm
computation. The gate mix is the diagnosis: every decision stopped at `no_active_alert_episode` or
`rebuild_fits_without_evicting`, and `pd_free_kv` was the constant 62,944 over every decision.

Under CLAUDE.md Rule 2 that is **UNEXERCISED** — the mechanism is reachable but no condition in the
run reaches it — and it is **an absent link, not a negative about the policy**. The user's diagnosis
is the one the gate mix supports: large non-urgent rebuilds rarely occur while histories stay warm,
so the remaining loss sits behind recall **question** prefills, which are neither rebuilds nor
evictions. A 6,000-token recall prompt delays an alert instant's first token through exactly the
same D162 queued-ahead term whether or not anything is evicted.

So the eviction gate is not a safety check that needs relaxing, it is **the wrong question**.
Protect-and-defer is therefore **left exactly as it is** — not loosened, not re-thresholded, not
re-run until it fires — and a second, differently-gated decision is added beside it. This is
recorded here so that it cannot later be read as a threshold having been moved after a null.

## 3. The inequality, in D191 item 1's ruled units

Gain and harm are both **counts of expected on-time cloud answers**, each device weighted by its own
`w_d`. **There is no division by the number served**: the target normalisation already lives inside
`w_d`. One comparison decides; any secondary key breaks only exact ties.

    defer iff   ( weighted gain  -  weighted harm )  >  w_R * MARGIN_CF ,   MARGIN_CF = 0.65824

For the question-deferral the two sides are named and both are inside the inequality:

* **gain** = the harm the deferral SAVES others, computed **per row**: a pending request whose own
  deadline has passed by the time the deferred prefill starts is saved; a row still ahead of it is
  not. `n_rows_saved` and `n_rows_still_harmed` travel on every decision, because "all the harm goes
  away" is the optimistic reading that makes a deferral look free.
* **harm** = the decider's **own loss**. Deferring to `deadline - kappa * service` leaves
  `kappa * service` of slack instead of the slack it has now, so the decider's own on-time
  probability falls, by `w_R * (p(engine, slack_now) - p(engine, kappa * service))`, on the same
  committed curve as every harm row. It is charged **before** the bar is consulted.

`w_j`, the harmed device's weight, sits **inside** the saving sum, one weight per row. `w_R`, the
decider's weight, scales **the bar**. Putting the harmed type's weight on the bar is the sign error
`cf_protect_defer` documents: harm and bar would scale together, the deciding ratio would not move,
and the deficit weight would be inert — Rule 2's `cancelled by geometry`.

`kappa = 1.5775406165458339`, the committed q90 of actual over predicted service, read through
`cf_margin.safety_factor(cf_cost.load_residuals())` — the same factor `v5/cf_planner.py:357` uses.
**Never chosen, never swept.** Its two committed caveats travel with every latest-start time: its
split is held-out-BY-ARM, not D125's "FIT/DEV", and the residual summary itself carries
`gate_status: FAILS`.

## 4. PRE-REGISTERED PASS AND FAILURE, at 1x, seeds 4 to 7

**Supplied by the user. Not recomputed, not negotiable after a cell.**

PASS requires **both** conjuncts, per seed:

1. **mean per-episode alert attainment ABOVE rung 3's**, which is

   | seed | 4 | 5 | 6 | 7 |
   |---|---|---|---|---|
   | rung 3 | 0.441 | 0.427 | 0.436 | 0.475 |

2. **robot on-time retention >= 0.90 of rung 3's gain over base.**

   | seed | 4 | 5 | 6 | 7 |
   |---|---|---|---|---|
   | base (`hybrid-F-lhreq-noc3`) | 35 | 27 | 41 | 19 |
   | rung 3 (`covex-v6-fair-c5attr`) | 122 | 114 | 109 | 84 |
   | rung 3's gain over base | 87 | 87 | 68 | 65 |
   | 0.90 of that gain | 78.3 | 78.3 | 61.2 | 58.5 |
   | **required rung-4 robot on time** | **>= 113.3** | **>= 105.3** | **>= 102.2** | **>= 77.5** |

   The required figure is `base + 0.90 * gain`, stated to one decimal so no rounding choice is made
   later. A count at or above it passes the conjunct.

**Reported beside it, every seat of it, and the third one may not be omitted:**

* **LATE ALERT FRAMES** — alert instants sent and answered after 1 s. The hypothesis is that they
  **fall**.
* **RECALL DEFERRALS** — count, and slack used (the deferral in seconds, as a distribution and not
  only a mean).
* **ANY RECALL MADE LATE BY A DEFERRAL** — D191 names this as the column that can turn a pass into a
  self-inflicted loss. The live figure is the scorer's. The dry arm also reports its own prediction
  of it (`rd_defer_own_p_after_zero`, `rd_defer_latest_start_infeasible`); the two are reported side
  by side and **neither is substituted for the other**.

**FAILURE CONDITION.** If the deferrals do not reduce late alert frames, protect-and-defer and
question-deferral are **REPORTED AS NOT WORKING**. They are **never tuned**. No threshold, no gate
and no horizon in either module is changed in response to a result.

**HARM BOUND**, carried forward unchanged from every cell of this grid: **robot late at most 10 per
seed**, flagged at once if exceeded, because deferring work can push the deferred work past its own
deadline.

**PORT RULE (CLAUDE.md "Citing results"), checked FIRST and before any score is read.** The count of
rung 4's characteristic decision — a question deferral, a rebuild deferral or a chunk — must be
**non-zero**. Zero is an **ABSENT LINK** and is reported as such, never as a negative about the
policy.

## 5. What is reported separately and must not be folded in

**Protect-and-defer at 0.25x is a memory-pressure result and is reported on its own.** It is not
folded into the 1x verdict, and it may not be quoted beside a 1x number without the memory setting
attached. A mechanism that fires only under memory pressure is a **finding**, stated that way.

## 6. The framing this rung has to beat

Every rule-based fix so far — the share floors, r1's release re-check, the C5 attribution rule,
rung 3's deficit ordering — lands somewhere on **one** alert-versus-recall trade-off curve: alert
attainment bought with recall on-time, or the reverse. Rung 4's claim is that a counterfactual that
prices the trade explicitly and defers in **time** rather than choosing in **priority** moves **off**
that curve: both axes at once, because the deferred work is not dropped, it is moved to slack that
was going to be wasted. If rung 4 lands on the same curve, it is a non-contribution however good one
axis looks, and it is reported as one.

## 7. Caveats fixed in advance

* **The 0.25x engine setting.** Any 0.25x cell of this rung is **REAL-ENGINE**
  (`--num-gpu-blocks-override 984 --max-model-len 15744`, in that exact order; the allowlist in
  `study_live2_pilot.py` is an exact list match and the same flags transposed still STOP), per the
  user's D189 ruling, with a **matched-memory `-off` control** alongside. A logical-only `_kv0.25`
  tag is not this condition and is labelled as a different one.
* **Dry cells do not exercise price.** The charge mode is unexercised dry (`covex-v6-rules` and
  `covex-v6-rules-wo` are byte-identical dry), so a dry cell proves the arithmetic is live and the
  switch reaches a decision; it says nothing about magnitude against a real engine.
* **The dry 0.25x control is degenerate.** The dry harness's `gpu_kv_fraction` comes from a live
  server and is identically 0.0, so dry evidence cannot substitute for the live matched control.
* **D188 freezes stand.** Floors and `W_max` frozen, `live2_qcache_key_fix` NOT enabled, and the
  `id(obs)` cache-key fix stays **OFF** (D190 (6): applied only when the final ladder is rerun
  together).
