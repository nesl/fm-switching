# WHY THE D250 GATE CELL LOST ~50 ROBOT ANSWERS: NEITHER STATED EXPLANATION. THE PLANNER NEVER READS THE DECLARED SIZE.

**CPU, committed artefacts, read-only. Nothing fixed, as the ruling required.**

## *** UNCONFIRMED, BY USER RULING 2026-11-25: THE "SMALLER TIER DROPPED THE PREFIXES" READING IS NOT YET A CAUSE. ***

**The user has identified a hole this diagnosis did not close.** *** THE TIER NEVER EXCEEDED 0.311 USAGE,
YET ROBOT P(cold) AT 30 TO 120 s IDLE WENT FROM 0.000 AT 27 GiB TO 0.400 AND 0.500 AT 13.5 GiB. A TIER AT 31
PERCENT DOES NOT EVICT WITHOUT A MECHANISM, AND NO MECHANISM IS NAMED BELOW. ***
**Everything else in this file stands: the declared size is an ABSENT LINK (two reads, one a counter and one
write-only), `OFFLOAD_TO_HOST` is absent in both cells, the 34 declines and their read at
`hybrid_arm.py:412,437` are measured, and the timing rules out policy feedback as the root. WHAT IS
UNCONFIRMED IS THE FIRST LINK ONLY: that the smaller tier is what made the engine drop the prefixes.**

**And one computation sharpens the hole rather than closing it:**
```
13.5 GiB cell : peak usage 0.3108 x 13.5 = 4.196 GiB held at peak
27   GiB cell : peak usage 0.1490 x 27.0 = 4.023 GiB held at peak
```
*** BOTH CELLS PEAKED AT ESSENTIALLY THE SAME ABSOLUTE BYTES, 4 PERCENT APART. SO THE TIER SIZE DID NOT
CHANGE WHAT THE ENGINE ACTUALLY HELD. THE ONLY THING THAT MOVED IS THE FRACTION, 31 PERCENT AGAINST 15. ***
**That makes one hypothesis testable and worth more than the rate-normalised argument this file originally
rested on: IF THE CONNECTOR EVICTS ON A WATERMARK EXPRESSED AS A FRACTION OF THE CONFIGURED SIZE, then an
identical 4.2 GiB working set crosses it in a 13.5 GiB tier and not in a 27 GiB one, with NEITHER TIER
ANYWHERE NEAR FULL. At any watermark between about 0.16 and 0.31 that is exactly what happens.**
**A CPU investigation is running against the installed vLLM offload connector source and the committed
artefacts, to settle three things: what the usage gauge measures and how often it updates against our
10 s sampling; the connector's host eviction policy and whether it evicts before the tier is full; and the
engine-side store and evict events around each loss, timestamped against host usage.** *** "THE DATA CANNOT
TELL" IS AN ACCEPTABLE OUTCOME AND IS BETTER THAN A MECHANISM THAT CANNOT BE EVIDENCED. UNTIL IT REPORTS,
NOTHING BELOW MAY BE CITED AS THE CAUSE OF THE DROP. ***

## *** THE ANSWER: NEITHER. ***

**The engine's 13.5 GiB host tier NEVER RAN OUT: usage max 0.3108, ZERO samples at or above 0.99, 0.90 or
even 0.50.** **And the planner NEVER READS the declared size.**
*** THE THIRD EXPLANATION: the smaller host tier made the engine actually DROP robot KV prefixes; the
coordinator's belief corrector read the engine's own per-request `cached_tokens` and flipped those sessions
to COLD; the arm's feasibility test then predicted a cold rebuild longer than the 3 s slack and DECLINED 34
ROBOT QUESTIONS BEFORE SENDING THEM AT ALL. THE POLICY REACTED TO A MEASURED CONSEQUENCE, NOT TO A DECLARED
NUMBER. ***

## COMPARISON 5 FIRST, BECAUSE IT SETTLES THE RULING'S QUESTION: THE DECLARED SIZE IS AN ABSENT LINK

`host_tier_tokens` has exactly **two reads** in the live2 run path:
1. **`cstate.py:545`** `if int(self.host_tier_tokens) > 0 and host_used > int(...): p["host_epochs_over_cap"] += 1`. **A COUNTER ONLY. It increments a diagnostic and changes nothing.**
2. **`cstate.py:708,712`** `_host_fraction()`, written into the Observation as `host_kv_fraction` at `cstate.py:698`.
*** AND `host_kv_fraction` IS WRITE-ONLY. A grep for `host_kv|host_tier|host_cap|host_fraction` across
`arms_v6*.py`, `*planner*.py` and `state*.py` returns ZERO LINES. No v6 arm, no `cf_planner`, no deficit
weighting reads it. ***
**Contrast the GPU branch nine lines below at `cstate.py:554-566`, which DOES read its cap to run the
eviction sweep: it reads `gpu_kv_tokens`, never `host_tier_tokens`, and `gpu_kv_tokens` is 31,472 IN BOTH
CELLS.**
*** SO "THE POLICY REACTED TO THE DECLARED SIZE" IS **FALSE**, AND FALSE IN THE EXACT SHAPE CLAUDE.md NAMES:
A VALUE SET, LOGGED, INSTRUMENTED PER CELL, AND NEVER CONSUMED. Under Rule 2's vocabulary the declared-size
hypothesis is UNEXPRESSIBLE: the harness computes the host fraction and discards the channel. ***

## AND A SECOND ABSENCE THAT MATTERS MORE FOR THE THESIS THAN THE FIRST

**`session_OFFLOAD_TO_HOST` is ABSENT IN BOTH CELLS, not merely equal.** It is the only action that sets
`desired_tier = "host"` (`coordinator.py:962-963`), it was never emitted, so `enact_placement`'s host branch
never ran and `offloaded = 0`. The arm's only placement channel is `KEEP_GPU_WARM`, which sets
`desired_tier = "gpu"` and only reorders the GPU eviction sweep.
*** A POLICY THAT NEVER PLACES ANYTHING ON THE HOST TIER CANNOT BE SIZING ITS BEHAVIOUR TO THAT TIER. ***

## THE CHAIN, WITH THE READ THAT TURNS A BELIEF INTO A LOST ANSWER

```
--kv-offloading-size 13.5   (the one differing input; GPU pool pinned at 1,968 x 16 = 31,488)
  -> the host tier holds the working set for LESS TIME, which the usage gauge cannot show:
     external prefix hit rate 20.2 pct against 33.0 pct; 2.7x store bytes per request; 0.63x load bytes
  -> per-request `cached_tokens` falls ON THE LONG ROBOT PREFIXES SPECIFICALLY
  -> coordinator.py:1941 -> engine_actions.py:368-371 : ct == 0 -> belief "cold"   (29 against 3)
  -> cstate.py:244-245,682 hands it to the arm as q.readiness = "COLD"
  -> hybrid_arm.py:412  est = recall_ttft_s(~14k tokens, "COLD")  >  qs (3 s)
  -> hybrid_arm.py:437  REJECT     -> coordinator.py:991,998-1009 declined, served_by device, NOTHING SENT
     34 declines against 1. `over_limit_infeasible` is 0 in both, so ALL 34 came from the slack branch.
```

## *** THE CLEANEST STRATUM: HALVING THE HOST TIER TOOK THE RETENTION HORIZON FROM OVER 120 s TO UNDER 30 s ***

**P(cold) by idle gap since the same robot's previous QUESTION:**
| gap | 13.5 GiB | 27 GiB |
|---|---|---|
| [0, 30) | 0.127 (n 55) | **0.000** (n 79) |
| **[30, 60)** | **0.400** (n 20) | **0.000** (n 27) |
| **[60, 120)** | **0.500** (n 6) | **0.000** (n 6) |
| [120, inf) | 0.900 (n 10) | 0.833 (n 12) |
*** AT 27 GiB A ROBOT HISTORY SURVIVES EVERY IDLE GAP UP TO 120 s WITH P(cold) EXACTLY 0.000 ACROSS 112
QUESTIONS. AT 13.5 GiB IT FAILS AT 30 s. AND THE TIER NEVER READ FULL. ***
**The zero is a real floor, not short-circuiting: the same column is 0.833 in the [120, inf) bucket.**

## THE TIMING PROVES THE DIRECTION AND RULES OUT POLICY FEEDBACK AS THE ROOT

**Touch decisions do not exist in either cell before t = 600 s. Yet in the 200 to 600 s window, with ZERO
touches in either cell, the small-tier robot `cached_fraction` is already 0.483 and 0.453 against 0.752 and
0.659. ITS FIRST DECLINE IS AT t = 316.27 s, INSIDE THAT WINDOW.** The engine-side divergence precedes any
differing placement action. The later policy divergence (touches 1,371 against 2,899, saturation guard
active 2,002 epochs against 274) is downstream amplification, not the cause.

## *** TWO CORRECTIONS TO THE PREMISE, BOTH MINE, NEITHER CHANGING THE CONCLUSION ***

**1. "121/132" IS THE UN-SUFFIXED CELL, NOT `_rep2`. `_rep2` IS 125/132.**
| cell | on-time | correct-by-deadline |
|---|---|---|
| gate, h0.5 | 72 | 72 = 49 cloud + 23 device |
| **`_rep2`** | **125** | **85 = 82 + 3** |
| un-suffixed | 121 | 82 |
| `_rep3` | 123 | 83 |
*** SO THE TRUE GAP IS 72 AGAINST 125 ON-TIME (53), AND 72 AGAINST 85 CORRECT-BY-DEADLINE (13). I quoted
121 as the `_rep2` figure and it was relayed and carried into a ruling. THIS IS THE SECOND TIME TODAY I HAVE
READ AN UN-SUFFIXED CELL AS ITS `_rep2`. *** **And the gate cell's 72 being both its on-time count AND its
correct-by-deadline count is a coincidence of two different fields, not an identity.**

**2. "SAME CODE EXCEPT THE HOST SIZE" IS FALSE AS STATED, AND HARMLESS IN EFFECT.** `_rep2` ran on
`experiments/` tree `3932b279c3ea`, the gate cell on `a7e21358c40d`; they differ by three run-path files
(`fleet/trace.py`, `fleet/emulator.py`, `run_live2_real.py`), all the D242 outage feature, off by default in
both. **Verified empirically rather than argued: identical `fairness_digest` and ALL 12,253
`(device_id, opportunity_id, t_opportunity)` tuples byte-identical, 132 robot questions at identical offer
times.** *** THE WORKLOAD IS THE SAME; THE CODE IS NOT LITERALLY THE SAME TREE. THIS PAIR SHOULD NOT STAND
AS THE FIRST SAME-CODE REPLICATE IN THE `L3_epg_rq30` CONDITION. ***

## ALTERNATIVES REJECTED, EACH ON EVIDENCE
**Engine out of host memory: REJECTED on the gauge, and the right frame is that the tier was never FULL but
was too small to RETAIN.** **Declared size: REJECTED on the absent read.** **Host CPU or RAM pressure:
REJECTED, `maxrss_kb` 147,476 against 147,112, `host_busy_frac` p50 0.0305 against 0.0301, 0 epoch
overruns.** **GPU cap: REJECTED, identical in both.** **The three-file code delta: rejected on content, and
flagged as the WEAKEST link in the chain rather than closed.**

## PROXY VALIDITY, STATED BECAUSE IT BOUNDS THE CLAIM
**`cached_tokens` is a proxy for GPU-KV residency, NOT for host residency, and `engine_actions.py:352-358`
says so in terms: it is an upper bound on reconstruction cost and NOT evidence the host tier was empty.**
*** FOR THE CLAIM BEING MADE IT IS NOT A PROXY AT ALL, IT IS THE ACTUAL INPUT THE POLICY DECIDES ON. It
would be invalid as evidence that the host tier was empty, which is NOT claimed. ***

## NOT A DEFECT IN THE ARM
**Declining a question whose predicted cold rebuild exceeds its deadline is the feasibility rule working as
specified. The arm was handed a worse world and made a defensible call in it.**
