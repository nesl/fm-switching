# SCOPING: SURVIVAL-AWARE WARM-STATE CONTINUITY UNDER HOST PRESSURE. THE EXPENSIVE HALF IS UNBUILDABLE AND THE CHEAPEST LEVER IS A CONFIG FLAG.

**SCOPE ONLY. No code, no edits, no cells, no GPU. Nothing committed to `experiments/`.**
**Frame, as ruled: the engine is a BLACK BOX; we cannot place KV and cannot see the host tier. EXCLUDED
FROM SCOPE: any change to engine eviction settings. That is harness, not policy.**

## *** AMENDMENT, SAME DAY: THE RANKING IS REORDERED, AND ONE CLAIM BELOW IS FALSE. ***

**The empirical leg of item 5 landed after this report was written. It CONFIRMS item 5 and WEAKENS lever A.**

### *** LEVER A WAS PRICED ON THE WRONG CELL'S NUMBER. LEVER B IS NOW THE FIRST MOVE. ***
**`P(host | not in GPU KV) = 0.5740` came from a probe captured during a `covex-v6-base` **kv0.25** cell: a
DIFFERENT ARM AND A DIFFERENT MEMORY CONDITION from the D250 cells. The cells that matter read much lower.**
| cell | P(host, not in GPU KV) | mixture at 14k | verdict at 2.956 s slack |
|---|---|---|---|
| **A, fair-final 13.5 GiB, THE D250 GATE CELL** | **0.1987** | **2.603 s** | SEND |
| B, covex-v6-base 13.5 GiB | 0.0420 | 3.004 s | *** DECLINE *** |
| C, fair-final 27 GiB | 0.3304 | 2.267 s | SEND |
| the probe originally cited | 0.5740 | 1.644 s | SEND |
*** SO THE LEVER STILL FLIPS THE DECLINE ON THE CELL THAT MATTERS, BUT THE MARGIN IS 0.353 s AND NOT 1.3 s,
AND THE BREAK-EVEN IS CLEARED 3.3x AND NOT 9.5x. AND THE ESTIMATE VARIES 14x ACROSS CELLS, 0.042 TO 0.574. ***
**In cell B the ratio is BELOW break-even, so the lever would correctly keep declining there. Reassuring
about calibration, sobering about robustness.**

**Three screws tighten on the same lever.**
1. *** THE 0.555 s HOST ESTIMATE IS FROM MEASUREMENTS TAKEN ONE REQUEST AT A TIME. The measured in-cell
   host-to-GPU bandwidth is 10x to 150x BELOW the isolated 47.6 GB/s. The two are not directly comparable, a
   fleet average over an interval against an isolated peak, BUT THE GAP EXCEEDS CONSISTENCY CHECK 1's 2x BAR
   AND MUST BE EXPLAINED BEFORE LEVER A IS COSTED: if a host reload under concurrency is materially slower
   than 0.555 s, THE 0.353 s MARGIN DISAPPEARS. ***
2. **Four touches in the gate cell became FULL RE-PREFILLS: 4 of 1,371, uncached up to 17,651 against a
   committed max of 15, residual p50 +1.374 s. Small, but it is the FIRST PER-REQUEST EVIDENCE that the
   halved tier drops prefixes.**
3. *** THE QUANTILE PROBLEM IS WORSE, NOT UNCHANGED. With P(cold) = 0.80 in the gate cell, a MEDIAN RULE NOW
   DECLINES TOO, because 0.199 < 0.5. ONLY AN EXPECTATION-BASED RULE ADMITS, SO LEVER A IS A DELIBERATE BET
   ON EXPECTED VALUE AGAINST A DEADLINE, LATE ON FOUR FIFTHS OF WHAT IT ADMITS. ***

*** REVISED ORDER: B, THEN A, THEN C. Lever B (turn C3 back on, 1 to 2 hours, no new code) is the clear
first move: a 467-token RECENT recall is feasible at ANY readiness, depends on NO residency estimate, and
carries NO lateness bet. The bandwidth question above is answered BEFORE any hours go to A. ***

### ITEM 5 IS NOW A REAL NEGATIVE RATHER THAN INCONCLUSIVE, AND THE CONTROL IS WHY
**Step 2 passes: host reloads measurably occurred in all five cells, and `kv_offload_load_bytes` divided by
`external_kv_transfer` equals 262,144 bytes per token in all five, independently confirming the committed
constant. Step 4 is built in: one cell has 5.3x fewer host tokens than another with indistinguishable
residuals.**
*** AND THE POSITIVE CONTROL DECIDED WHICH MEASURE TO TRUST, WHICH IS CHECK 7 APPLIED TO THE INSTRUMENT
RATHER THAN THE RESULT. On requests whose OWN uncached work is 3 tokens, the D162 residual reads touch p50
at +0.019 / -0.012 / -0.005 / -0.025 s, straddling zero, so it is SOUND. The cost-curve-rate residual reads
+0.728 s on THOSE SAME REQUESTS with a minimum of +0.063 and NOT ONE ROW NEAR ZERO, so it is BROKEN. EVERY
SEPARABILITY CLAIM RESTS ON THE MEASURE THAT PASSED. ***
**Physical bound beyond statistics: sustained host-to-GPU bandwidth is p50 0.32 to 0.53 GB/s against a
residual IQR of 107 to 559 ms. Essentially every candidate band fails the rate bar, one by 377x at an
implied 541 GB/s, ABOVE HBM BANDWIDTH. And the implied rate CLIMBS MONOTONICALLY with bucket size, 4,236 to
82,739 tok/s, which is the signature of A FIXED PER-REQUEST OFFSET, NOT A TRANSFER: a transfer gives a
CONSTANT implied rate.**
**No size-proportional band: `corr(residual, cached_tokens)` is -0.067, +0.103, +0.068 across three cells,
so it does not replicate, while `corr(residual, queue_uncached_ahead)` is +0.771. THE RESIDUAL TRACKS THE
QUEUE, NOT THE PREFIX.**
**The self-referential threat is acknowledged and answered: the queue term was RECONSTRUCTED from submit-to-
first-token overlaps, so a request delayed by a reload widens its own interval and the term would ABSORB the
host signal. TWO CHECKS THAT USE NO QUEUE TERM FIND THE SAME NOTHING: the host-active against host-quiet
contrast, at most 0.008 s and RUNNING THE WRONG WAY in several rows, which a real reload cost cannot do; and
the physical bandwidth bound.** *** 3(d) IS CLOSED BY TWO INDEPENDENT ROUTES. DO NOT REOPEN IT ON A TIMING
ARGUMENT. ***

### *** A CLAIM BELOW IS FALSE AND I COMMITTED IT ***
**This report states the 13.5 GiB D250 cell is "the ONLY cell in the whole live2 tree with
`host_tier_gib != 27.0`". THAT IS WRONG.** There is a second:
`covex-v6-base_n16_s4_1200s_h27_3t_kv0.5r_h0.5_L3_epg_rq30`, `host_tier_gib` 13.5, verdict OK, **which is
the FIRST OF THE SIX D250 BASELINES.** A listing for `_h0.5` returns four paths, two of them frozen_test
runs. **The 22-cell census was correctly scoped to `header.arm == covex-v6-fair-final`, so that baseline was
outside it; the stronger "only cell in the tree" claim was not scoped and is false.**

### TWO THINGS NOW PROVEN RATHER THAN ASSERTED
**CACHING, named as CLAUDE.md requires: ALL FIVE CELLS RAN WITH PREFIX CACHING ENABLED, recorded the hard
way as `--no-enable-prefix-caching` at argv index 13 OVERRIDDEN by `--enable-prefix-caching` at index 27,
with `engine_reported.enable_prefix_caching` True. THESE ARE WARM-SERVING CONDITIONS THROUGHOUT: nothing in
this corpus is a cold measurement and nothing above compares across a warm/cold boundary. It is also a live
instance of the last-wins argv hazard.**
*** SINGLE-SHOT TRAFFIC IS COLD BY CONSTRUCTION: `cached_tokens` is 0 on every one of 356 single-shot
requests, max 0, in every cell. SO THE `kind == "recall"` HAZARD IS WORSE THAN DILUTION - IT MIXES AN
ALL-COLD POPULATION WITH AN 88-PERCENT-WARM ONE UNDER ONE LABEL. The `robo` prefix filter is not optional. ***

---

## 1. WHAT THE RUN PATH KNOWS TODAY

| quantity | exists | READ at a site that changes a decision |
|---|---|---|
| per-request `cached_tokens` | yes | **coordinator-side ONLY** (`coordinator.py:1920` into the belief corrector). **NO arm in the chain reads it** |
| `belief` | yes | **YES, arm-side**: `arms_v6state.py:416` gates the RELOAD candidate; `cstate.py:674-676` to `q.readiness`, consumed at `hybrid_arm.py:412` |
| `measured_tier` | yes | coordinator-side only. Never reaches an arm |
| **idle time** | partially | *** NO idle-time survival read ANYWHERE. `last_touch_s` has ONE decision read, `cstate.py:563`, the GPU eviction sort key, a coordinator LRU tiebreak *** |
| **survival** | *** ABSENT *** | **no survival model exists in the live path at all** |

*** BOTH NAMED CHECKS COME BACK ABSENT, AND ONE OF THEM ALREADY SAID SO. *** The committed audit
`d216_survival_predictor_readsites.py` answers this exact question "NO" in its own `ANSWER` field, with three
proofs: the pricing functions are handed a belief and a token count **and nothing else**, so a function not
given a quantity cannot consult it; the price is unchanged when the pool is scaled 4x; and every writer of
`SessionRec.belief` sets a ONE-HOT dict, so `PURE_TIER_MIN_BELIEF = 0.95` can never refuse. Its own summary:
**"the last observed or enacted tier, one-hot, carried forward unchanged. Not time, not a constant, not the
pool: A STALE OBSERVATION STANDING IN FOR A PREDICTION."** `should_touch` takes belief, prefix tokens, costs
and a budget flag, with **no idle time and no host size.**

**Lead confirmations: `host_tier_tokens` is ABSENT as a policy input (two reads, a diagnostic counter and a
write-only `host_kv_fraction` with ZERO non-test references). `OFFLOAD_TO_HOST` is emitted by NO arm; the
only `SessionAction` emitters send `KEEP_GPU_WARM` only.**
*** ONE CORRECTION TO CLAUDE.md ITSELF, WHICH A FUTURE READER WILL TRIP ON: `desired_tier` IS NO LONGER
WRITE-ONLY. D133 Part A made it read at `cstate.py:527`, `:530`, `:562`. The lesson stands but the
illustration is stale. `host_kv_fraction` IS THE CURRENT GENUINE INSTANCE. ***

### ITEM 3(d) IS CLOSED BY MEASUREMENT, NOT BY A MISSED KEY NAME
**The whole per-request schema is `UsageInfo` plus `PromptTokenUsageInfo{cached_tokens, created_cache_tokens,
multimodal_tokens}`. A HOST HIT AND A GPU HIT ARE BOTH FOLDED INTO `cached_tokens` AND CANNOT BE TOLD APART.**
Confirmed from the counter side (`prompt_tokens_cached_total` = local hit + external transfer exactly) and
recorded in code as `PER_REQUEST_HOST_SIGNAL_AVAILABLE = False`. **Evidence is an OBSERVED probe on the live
H100, not an inference.** *** SO THE THIRD COST TIER CANNOT BE BUILT AND THE USER'S OWN CONDITION ON IT
FAILS. What survives is not a tier but a MIXTURE PRIOR, which needs no per-request signal. ***

## 2. PUBLISHING HOST COUNTERS: YES, AND MY EPOCH ARITHMETIC WAS WRONG BY 50x IN THE FAVOURABLE DIRECTION

**I estimated the gauge as 100x slower than the epoch rate. There are TWO channels and I had costed the wrong
one.** The 10 s figure is the DRIVER'S SHELL LOOP writing a log file that nothing in the live path reads. The
in-process channel is `METRICS_POLL_INTERVAL_S = 0.2`, polled in a background thread.
*** DECISION_PERIOD_S = 0.1, SO THE GAUGE REFRESHES ONCE PER TWO EPOCHS, NOT ONCE PER HUNDRED. STALENESS IS
AT MOST 200 ms, AND 200 ms IS WORTH ACTING ON. ***
**And the keys are ALREADY allow-listed and merged: `PUBLISHED_ENGINE_KEYS` already carries
`kv_offload_cpu_cache_usage_perc`, the store and load byte and time totals, and the external prefix hit and
query counters, and `coordinator.py:489` refreshes `st.metrics` EVERY EPOCH. The only missing hop is lifting
them into the frozen `CloudState`. 2 to 3 hours with proofs.**
*** ONE HARD CAVEAT THAT BOUNDS 3(a) AND 3(b): NO COMMITTED CELL IN THIS ARM FAMILY WAS EVER SCRAPED. All 22
`covex-v6-fair-final` cells carry `metrics_health.state = never_scraped`, so `gpu_kv_fraction` is identically
0.0 in every one. Publishing host usage yields a field live only in FUTURE cells, with NO committed data to
validate a host-conditioned model against. ***

## 3 AND 7. WHAT IS REACHABLE, AND THE TWO DEFINITION TRAPS

*** HOST-WARM IS STRUCTURALLY UNREACHABLE BY TWO INDEPENDENT FACTS, AND THIS IS A STATEMENT ABOUT THE
THESIS RATHER THAN ABOUT RELOAD. *** `readiness()` requires `believed_tier() == "host"`, and both writers of
a host belief are dead: one requires `external_tokens`, which returns None on every request of this engine by
measurement; the other requires `OFFLOAD_TO_HOST`, which no arm emits. **The planner's own detail field
already records "cold 14,472 / gpu 1,442 / host NEVER over 39 committed 16-device cells", and
`arms_builder.py:26` says it in one line: "HOST-WARM is unreachable."**
*** SO THE HOST TIER DOES NOT EXIST AS A POLICY STATE IN THIS HARNESS. Together with the declared size never
being read and `OFFLOAD_TO_HOST` never being emitted, that is THREE INDEPENDENT WAYS THE HOST TIER IS
INVISIBLE TO THE POLICY. ***

**TRAP 1, a definition audit: SLICE NAMES TWO DIFFERENT OBJECTS.** The state planner's candidate, which the
D259 probe counted at zero, and a live `warm_ahead` slicing at 1,024 tokens that is ON BY DEFAULT in rung 3
with firing counters. **"SLICE chosen = 0" MUST NOT be read as "slicing does not happen".** Neither can
convert a decline, because both are scoped to background warming only, never a deadline request.

*** TRAP 2, AND IT IS LEVER B: C3 DEGRADATION IS BUILT, READ, AND SWITCHED OFF BY ONE FLAG. *** The branch at
`hybrid_arm.py:456-478` converts a REJECT or DEFER into `CLOUD, representation="RECENT"` at 467 tokens, and
the representation channel is LIVE AND READ at `coordinator.py:1428`. **But `V5RULES2_BASE =
"hybrid-F-lhreq-noc3"` with `c3=False`, and nothing in the covex ladder turns it back on.** *** SO THE 34
DECLINES SURVIVE TO `hybrid_arm.py:437` BECAUSE A FLAG IS OFF, AND THAT FLAG WAS SET UNDER D152 (2) AS A
DELIBERATE AND REVISITABLE INTERIM REFERENCE, NOT A STRUCTURAL FACT. ***

## 5. TIMING CANNOT CLASSIFY GPU HIT FROM HOST RELOAD. SETTLED WITHOUT FITTING ANYTHING.

```
signal : HOST minus GPU TTFT excess   0.077 s at 11k ,  0.127 s at 28k   (StudyRH5 Part A)
physical cross-check  2.884 GB / 47.6 GB/s = 0.061 s ; 7.340 / 52.9 = 0.139 s  -> within 20 pct, PASSES
noise  : touch TTFT p10 to p90 = 0.873 s, of which 70 to 98 pct is QUEUEING
*** SIGNAL-TO-NOISE = 11.3x AGAINST. THE MODES CANNOT SEPARATE. 3(d) IS CLOSED FOR GOOD. ***
```
**The methodological guard held: no marginal medians were combined. The committed curves gave signal and
noise separately on the same engine, which is stronger than a residual histogram.**
*** AND THE REFRAME THAT MATTERS: THE VALUE OF A HOST SIGNAL IS NOT COST ACCURACY, IT IS A FEASIBILITY FLIP.
THE COST GAP IS 0.077 s AND THE DECISION GAP IS 2.556 s, A FACTOR OF 33. At 14k tokens COLD prices 3.111 s
and declines while HOST prices 0.555 s and serves. ***

## 6. TOUCH AS A PROBE: READ, BUT NOT ACCUMULATED, AND REFUSED EXACTLY WHEN YOU WANT IT

**A touch's `cached_tokens` IS read: it runs the belief corrector like any other request. What is absent is
ACCUMULATION: it is consumed as a one-hot tier latch overwritten by the next observation, with no memory of
the gap it was observed across. So 3(a) is a NEW READ OF AN EXISTING PUBLISHED VALUE plus an accumulator,
not new plumbing.** Cost per touch is **0.002736 GPU-s**, so 2,899 touches cost about 7.9 GPU-s over 1,200 s.
Price is not the constraint. The constraints are:
*** `mixed_touch_guard` REFUSES A TOUCH EXACTLY WHEN THE BELIEF SAYS COLD, WHICH IS EXACTLY WHEN YOU MOST
WANT TO PROBE. SO TOUCH CANNOT BE USED AS A PROBE OF A COLD-BELIEVED SESSION TODAY, BY DESIGN. *** Changing
it is a methodological change. **And touches do not exist before t = 600 s while the first decline is at
t = 316 s, so they arrive after the damage.**

## *** THE CEILING, AND IT CORRECTS MY OWN YARDSTICK DOWNWARD BY 2.5x ***

| cell | on-time | correct-by-deadline |
|---|---|---|
| gate, 13.5 GiB | 72 | **72 = 49 cloud + 23 device** |
| `_rep2`, the right comparator | 125 | **85 = 82 cloud + 3 device** |

**I set the yardstick at "cloud-only 49 against 82", a gap of 33.** *** THE cbd GAP IS 13, NOT 33, BECAUSE
THE DEVICE ALREADY RECOVERED 23 OF THE DECLINED QUESTIONS CORRECTLY AND ON TIME. SO A LEVER THAT CONVERTS A
DECLINE INTO A CLOUD SEND GAINS AT MOST ABOUT 13 cbd, PLUS AN ACCURACY UPGRADE ON THOSE 23 - AND IT CAN
**LOSE**, BECAUSE DECLINING CURRENTLY HANDS THE QUESTION TO A DEVICE THAT ANSWERS ON TIME. ***

## THE RANKING, BY BENEFIT PER BUILD HOUR AT THE D250 CONDITION

| rank | lever | ceiling | cost |
|---|---|---|---|
| **1** | *** MIXTURE-PRIOR PRICING of a cold-believed recall *** | up to 34 declines, realistic net ~13 cbd | **4 to 6 h** |
| **2** | *** TURN C3 BACK ON, on a new labelled arm *** | up to 34 declines converted to 467-token RECENT sends | *** 1 to 2 h, ONE FLAG *** |
| 3 | `P(still cached | idle gap)`, unconditioned | indirect; the input 1 and 4 need | 6 to 8 h |
| 4 | TOUCH timed by (3) | **small. RANK IT LOW EVEN THOUGH IT IS CHEAP** | 4 h on top of 3 |
| 5 | host usage in Observation | **ZERO today, no consumer exists** | 2 to 3 h |
| 6 | third cost tier, HOST RELOAD | **DO NOT BUILD** | blocked |
| 7 | SLICE and warm-ahead as decline alternatives | **ZERO for declines**, scoped to background only | n/a |

### LEVER 1 IN FULL, BECAUSE ITS COUNTER-ARGUMENT IS THE WHOLE DESIGN DECISION
**The arm prices a cold-believed recall as hard COLD, but "cold" means NOT IN GPU KV, and the engine's own
committed counters say P(host | not in GPU KV) = 4,943,072 / 8,612,247 = 0.5740.**
```
at 14k tokens : mixture 0.574 x 0.555 + 0.426 x 3.111 = 1.644 s  against slack 2.956  -> SERVES
                hard COLD                              3.111 s                        -> DECLINES
break-even P(host) = (3.111 - 2.956) / (3.111 - 0.555) = 0.0606 , CLEARED 9.5x
```
**Needs NO per-request signal, NO engine change, NO new plumbing.**
*** THE COUNTER-ARGUMENT, STATED BY THE SCOPING ITSELF: THIS PUTS AN **EXPECTATION** INTO A **FEASIBILITY**
TEST. With P(cold) = 0.426 the p90 of a two-point mixture IS the COLD value, so a p90 rule still declines
and a median rule is LATE ON 43 PERCENT OF WHAT IT ADMITS - and lateness may be worse than the device answer
it gave up. THE DELIVERABLE IS THE QUANTILE, AND THAT IS A USER PARAMETER, NOT A MODELLING CHOICE. ***
**Further caveats: the 0.574 comes from a `kv0.25` cell and is token-weighted over dashcam-dominated traffic
rather than robot-specific, so it needs per-condition recalibration. The counters are in every cell's
`host_counters_d211.log`, so recalibration is offline and cheap.**

## FIVE THINGS ABOUT THE OFFLINE FIT, BEFORE ANY HOURS ARE SPENT ON LEVER 3

1. **The committed fitting script DROPS the 13.5 GiB cell by accident: its regex is anchored and the
   `_preD249` suffix fails it. It has NO `_h0.5` discriminator, so a halved cell could be POOLED INTO THE
   27 GiB KEY SILENTLY. Only 8 of 22 cells match it, and its repo path is hard-coded to another box.**
2. **NO committed script produces the idle-gap table at all. It came from an uncommitted ad-hoc analysis.**
3. *** THE COLD CASES ARE SELECTIVELY MISSING FROM `request.jsonl`: the 34 declined questions have an
   outcomes row and NO request row. THAT IS INFORMATIVE RIGHT-CENSORING, BIASING ANY REQUEST-ROW FIT TOWARD
   OPTIMISM EXACTLY WHERE IT MATTERS. ***
4. **The corpus CANNOT identify a decay horizon at 27 GiB: about 90 pct of usable pairs are in a degenerate
   [0,1) s bucket, and it is flat zero out to 120 s with almost no mass beyond.**
5. **The only two cells with real cold mass are the 13.5 GiB D250 cell and the robot-heavy `_c3-11-2` cell,
   so a survival model on this corpus is fit almost entirely on ONE RUN PER REGIME.**

## ITEM 4: A NEW ARM, AND THE SEQUENCING IS NOT THE STRONGEST REASON

*** `covex-v6-fair-final-q` DOES NOT EXIST ON ORIGIN. `git grep` for it over `experiments/` returns ZERO
lines and the registry does not list it. SO THE QUESTION "`-q` OR A NEW ARM" HAS A PRIOR ANSWER: YOU CANNOT
PUT IT IN `-q`, BECAUSE `-q` IS NOT THERE TO PUT IT IN. ***
**And the sequencing compounds it: landing this into the scratch `-q` build would make the D265 byte-identity
proof cover a larger unproven change, and the pre-registered gate cell would test an arm that is not the one
pre-registered. D261 scopes the D259 margin to `-q` ALONE, so `-q` is the one arm whose margin is specially
calibrated and the one whose behaviour you least want to perturb.**
**RECOMMENDATION: a NEW LABELLED ARM over committed rung 3, default OFF, registered beside the `-ptg`
variants. That preserves the D265 proof and the pre-registered gate, respects D79, and sidesteps a blocker:
rung 3's TOUCH is live and firing at 2,899 touches, whereas `-q`'s is UNREACHABLE at all 61,678 decisions.**
**While the D250 first link was open, 3(a) could claim only a GPU-KV residency hazard, unconditioned on host
usage. The connector investigation has since RESOLVED that link (the tier WAS full; the gauge measures
pinning, not occupancy), so the conditioning variable, if added later, is OCCUPANCY AS A FRACTION OF
CONFIGURED SIZE and not absolute bytes.**

## OWED
**No E-id exists for this design. The `StudyD<nnn>` series ends at `StudyD249-QPLANNER`, so a row in
`research/EXPERIMENTS.md` is a stopping condition before any of it starts.**
**Numbers passed through rather than independently re-read: the 34 declines, the 2,899 and 1,371 touch
counts, `touch_refused_guard` 63, and the 0.311 host peak, all from the handoff and the D250 diagnosis.**
