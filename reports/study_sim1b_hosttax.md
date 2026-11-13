# StudySIM1b-hosttax — what the KV-HOST episodic slowdown actually is

**CPU only on the flash host. No GPU, no model server, no inference.** Steps 0-3 are computed from committed per-request records (StudyE10b, StudyE10c, StudyE10e); Steps 4-5 run the offline simulator. No result marked INVALID is used. This is not a baseline study: no policy is compared and our scheduler is not in it.

**Headline.** The KV-HOST episodic slowdown is a per-request **MODE COST** — hypothesis (i) — paid whenever the host-offload connector is enabled, with **no warm session in the system at all**. It is not the per-overlap cost of hypothesis (ii): the overlap penalty is real, but it is the same size in the KV-GPU control cells as in the KV-HOST cells, so it is not host-specific. Modelling the mode cost closes most of StudySIM1's p50 gap (KV-HOST k = 16 at N = 1, 25 %: simulated p50 0.144 s -> 0.1825 s against a measured 0.180 s) and raises the gate from 18/29 and 10/16 to **20/29 and 11/16**. **The gate still FAILS** (69 % against an 80 % bar), so the pre-registered stopping condition fires and this report stops rather than iterating.

---

## 0. What was run, and in what order

1. SIM1's committed calibration was re-run unchanged as a reproduction check. It did not reproduce bit-exactly, and section 1 is that finding and its fix.
2. The two pre-registration rows (StudySIM1b-hosttax, StudySIM1c-scoped) were added to `research/EXPERIMENTS.md`.
3. Steps 0-3 below were computed from committed records.
4. The supported effect was added to the engine as an **OFF-by-default option** and SIM1's gate was re-run once with it ON.

One ordering disclosure: the Step-1 contrast (KV-HOST k = 0 against KV-GPU k = 0) was first computed as an exploratory check before the pre-registration row was written. That changes nothing about the decision, because **the decision rule in Step 3 was fixed by the specification before any of these numbers existed** and was not chosen after seeing them. It is recorded here rather than left implicit.

## 1. A reproducibility defect in StudySIM1, found by the reproduction check

Re-running `calibrate.py` unchanged reproduced all 16 ladders, all 8 p50 cells and 27 of the 29 p99 cells byte-identically. The two KV-GPU k = 8 collapse cells did not. The cause is in the warm-miss draw, which was `hash((sid, int(ta))) % 100`:

* Python randomises `hash()` of a tuple containing a string **per process**, so the committed numbers were not reproducible by any run.
* The draw was keyed on the touch alone, so **all five arrival seeds of a cell shared one miss pattern** and the reported 5-seed spread understated the seed variance in every warm cell.

The draw is now keyed on (cell, arrival seed) with `np.random.default_rng`, like every other stochastic element of a cell. Before and after, at 25 % load:

| cell | committed | 5 hash seeds (0-4) | 20-hash-seed miss count | crc32 draw | **seed-keyed (new)** | measured |
|---|---|---|---|---|---|---|
| KV-GPU k = 8, N = 1 | 125.257 s | 111.12-140.66 s | 162-186 of 216 | 147.79 s | **138.737 s** (134.42-143.32) | 192.8 s |
| KV-GPU k = 8, N = 3 | 124.254 s | 109.94-139.88 s | 162-186 of 216 | 146.42 s | **132.441 s** (126.78-141.40) | 183.3 s |

Nothing else moves: all other 27 p99 cells, all 16 ladders and all 8 p50 cells are numerically identical, **no cell changes its pass/fail status**, and the gate verdict is unchanged at 18/29 and 10/16. Both cells pass on the pre-registered collapse rule (both numbers far above the budget), never on the ratio. The two committed values are marked superseded in the StudySIM1-mixed row.

The only other non-deterministic construct anywhere in `experiments/orchestration/sim/` or `experiments/orchestration/baselines/` is `naive.py`'s `_unit_hash`, which already uses `zlib.crc32`. There is no unseeded `random`, no set-order iteration and every policy takes an explicit `reset(seed)`.

## 2. Step 0 — clock and field audit

One per-cell clock for every kind. Episodic and `cold_recall` records carry `t_sched` and `dispatch_late_s`; recall records carry `t_submit`, `latency_s` and `t_end` directly.

| check | rule | n | worst deviation | verdict |
|---|---|---|---|---|
| `recall_t_end_identity` | t_end = t_submit + latency_s within 1.5 ms (three millisecond-rounded fields) | 17234 | 0.00100 s | PASS |
| `episodic_ttft_identity` | ttft_s = service_ttft_s + dispatch_late_s within 1.5 ms | 133599 | 0.00010 s | PASS |
| `interleaving` | in every mixed cell the episodic and recall submit spans overlap on one clock | 59 cells | min overlap fraction 0.713 | PASS |

The `t_end` identity holds to 1.0 ms exactly. `t_submit`, `latency_s` and `t_end` are each committed rounded to the millisecond, so the identity can miss by up to half a unit on each of the three; the tolerance is 1.5 ms for that reason and the worst observed deviation is reported so the reader can see it is the rounding and not a clock offset.

**Per-kind field schema** (the fields each kind carries, from 53700 + 75855 + 22861 committed records):

| kind | timing fields | size fields | identity fields |
|---|---|---|---|
| `episodic` | `t_sched`, `dispatch_late_s`, `ttft_s`, `service_ttft_s`, `total_s` | `prompt_tokens`, `cached_tokens`, `completion_tokens`, `body_mb` | `request_id`, `cell`, `kv`, `k`, `r`, `N`, `frac`, `rate`, `in_window` |
| `cold_recall` | `t_sched`, `dispatch_late_s`, `ttft_s`, `service_ttft_s`, `total_s` | `prompt_tokens`, `expected_prompt_tokens`, `cached_tokens`, `n_frames`, `body_mb` | as episodic |
| `recall_append` / `recall_escalation` / `recall_warmup` | `t_sched`, `t_submit`, `submit_lag_s`, `ttft_s`, `latency_s`, `t_end` | `prompt_tokens`, `cached_tokens`, `n_frames`, `n_new_frames`, `body_mb`, `full_equiv_mb` | `session`, `video_id`, `session_t`, `question_id`, `policy`, `fmt`, `cadence`, `D`, `offload_gib`, plus the cell fields |

Episodic submit time is `t_sched + dispatch_late_s` throughout, and the identity `ttft_s = service_ttft_s + dispatch_late_s` holds to 0.1 ms over 133599 records, which is what licenses using it.

## 3. Step 1 — the MODE COST, from held-out cells

StudyE10b ran episodic-only ladders (k = 0 warm sessions, r = 0 cold recall) under **both** KV modes. Those cells contain no recall work of any kind, and **none of them appears in any StudySIM1 gate cell**, so they are a genuinely held-out measurement of what enabling the host-offload connector costs by itself.

| N | load | KV-GPU p50 | KV-HOST p50 | difference | 95 % CI | ratio | KV-GPU p10 | KV-HOST p10 | KV-GPU p99 | KV-HOST p99 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 25 % | 0.1301 | 0.1715 | **+0.0414** | [+0.0384, +0.0456] | 1.318 | 0.1198 | 0.1418 | 0.2859 | 0.3076 |
| 1 | 50 % | 0.1724 | 0.2079 | **+0.0355** | [+0.0290, +0.0405] | 1.206 | 0.1239 | 0.1525 | 0.4605 | 0.4618 |
| 1 | 75 % | 0.2931 | 0.2925 | **-0.0006** | [-0.0129, +0.0139] | 0.998 | 0.1458 | 0.1540 | 1.5549 | 1.6077 |
| 1 | 90 % | 0.7257 | 0.7427 | **+0.0170** | [-0.0128, +0.0484] | 1.023 | 0.2677 | 0.2767 | 3.0687 | 2.9993 |
| 3 | 25 % | 0.2211 | 0.2323 | **+0.0112** | [+0.0061, +0.0140] | 1.051 | 0.2165 | 0.2205 | 0.4776 | 0.4590 |
| 3 | 50 % | 0.2529 | 0.2700 | **+0.0171** | [+0.0016, +0.0302] | 1.067 | 0.2182 | 0.2333 | 0.9883 | 1.0285 |
| 3 | 75 % | 0.5286 | 0.5665 | **+0.0379** | [-0.0310, +0.0985] | 1.072 | 0.2304 | 0.2579 | 3.2595 | 3.1856 |
| 3 | 90 % | 0.9571 | 0.9633 | **+0.0062** | [-0.0810, +0.1144] | 1.006 | 0.2644 | 0.2886 | 3.1561 | 3.1271 |

Each cell has 902 and 287 usable in-window episodic requests at N = 1 and N = 3 respectively at 25 % load, rising to 3333 and 1153 at 90 %. The bootstrap is 2,000 resamples, seed 0, resampling requests within cell.

**N = 3 cells exist** and are reported above (`E10B_KVHOST_k0_r0_N3_L{25,50,75,90}`).

### Additive or multiplicative?

| N | differences across load | ratios across load | CV of the difference | CV of (ratio - 1) |
|---|---|---|---|---|
| 1 | +0.0414, +0.0355, -0.0006, +0.0170 | 1.318, 1.206, 0.998, 1.023 | 0.707 | 0.969 |
| 3 | +0.0112, +0.0171, +0.0379, +0.0062 | 1.051, 1.067, 1.072, 1.006 | 0.667 | 0.526 |

At N = 1, where the effect is significant, the **additive** form is the more constant of the two (CV 0.71 against 0.97) and it is the form the option uses. Neither form is constant across the whole ladder, and that is the finding of the next paragraph, not a defect of the fit.

### The effect is on the non-blocking path, not on engine time

The difference is largest at **low** load (+0.0414 s at 25 %, +0.0355 s at 50 % at N = 1) and is gone at high load (-0.0006 s at 75 %, +0.0170 s at 90 %, both CIs spanning zero). An added per-request *service* time would be amplified by queueing as load rises, not erased by it. So whatever the connector costs is not engine occupancy: it is time on the request-handling path that overlaps other work once the engine is busy. The option charges it as non-blocking time for that reason. **The vanishing at high load is not reproduced by the option**, and that is its stated limit; every KV-HOST cell in the gate runs at 10-40 % load, inside the regime where the estimate was taken.

### The noise floor

StudyE10b and StudyE10c ran the same configuration (E0 / KV-GPU k = 0 / r = 0) weeks apart on the same host. Whatever separates their medians is what a difference of this size is worth before any mechanism is invoked.

| N | StudyE10b cell | p50 | StudyE10c cell | p50 | drift | 95 % CI |
|---|---|---|---|---|---|---|
| 1 | `E10B_KVGPU_k0_r0_N1_L25` | 0.1301 | `E10C_E0_C0_N1_L25` | 0.1466 | +0.0165 | [+0.0141, +0.0205] |
| 3 | `E10B_KVGPU_k0_r0_N3_L25` | 0.2211 | `E10C_E0_C0_N3_L25` | 0.2573 | +0.0362 | [+0.0340, +0.0385] |
| 1 | `E10B_KVGPU_k0_r0_N1_L50` | 0.1724 | `E10C_E0_C0_N1_L50` | 0.1874 | +0.0150 | [+0.0074, +0.0201] |
| 3 | `E10B_KVGPU_k0_r0_N3_L50` | 0.2529 | `E10C_E0_C0_N3_L50` | 0.2938 | +0.0409 | [+0.0238, +0.0548] |

The floor is taken **per N** at 25 % load, the lowest level both studies share: **0.0165 s at N = 1 and 0.0362 s at N = 3**. The N = 3 drift is more than twice the N = 1 drift, which is why a single pooled floor would have been the wrong object.

**Against its own floor, the mode cost clears at N = 1 and does not clear at N = 3.** At N = 1 the 25 % and 50 % differences (+0.0414 and +0.0355 s) are both above the 0.0165 s floor with CIs excluding zero. At N = 3 the differences (+0.0112 and +0.0171 s) have CIs excluding zero but sit **below** the 0.0362 s drift floor for N = 3, so they are not separable from between-study drift and are not used.

## 4. Step 2 — the OVERLAP COST, and why it is not host-specific

Every usable in-window episodic request in every KV-HOST cell with k > 0 (StudyE10b, StudyE10c at every engine configuration E0/E1/E2/E4, and StudyE10e's C4 cells) is labelled OVERLAP if `[submit, submit + ttft]` intersects any `recall_append` / `recall_escalation` / `recall_warmup` interval `[t_submit, t_end]`, else CLEAR. Every KV-GPU cell with k in {2, 4} is the control: those are the warm-session cells where StudyE10b measured **no collapse** (0 misses of 54 at k = 2, 1 of 106 at k = 4).

**2409 episodic requests were EXCLUDED** because their interval overlapped a `cold_recall`. That is the head-of-line hold StudySIM1 already models; counting it here would measure the same mechanism twice.

50 cells were labelled: 45 KV-HOST and 5 KV-GPU control.

### The cell-matched comparison — the one the verdict reads

| N | load | KV-HOST cells: OVERLAP - CLEAR p50 | median | KV-GPU control cells | median | host exceeds control? |
|---|---|---|---|---|---|---|
| 1 | 25 % | +0.0653, +0.0564, +0.0650, +0.0501, +0.0472, +0.0500, +0.0526 | **+0.0526** | +0.0597, +0.0551 | **+0.0574** | **no** |
| 3 | 25 % | +0.0671, +0.0643, +0.0209 | **+0.0643** | +0.0242 | **+0.0242** | yes |
| 3 | 50 % | +0.1732, +1.4685, +0.1453 | **+0.1732** | +0.0883, +1.5941 | **+0.8412** | **no** |

The host exceeds the control in **1 of 3** matched comparisons. At N = 1, 25 % - the only matched point with several cells on both sides - the KV-HOST penalty (+0.047 to +0.065 s, median +0.0526) and the KV-GPU penalty (+0.0551 and +0.0597 s, median +0.0574) are the same size. **Having a recall request in flight costs an episodic request about 0.05-0.07 s whichever KV mode is in use.** That is a real effect and it is not what distinguishes KV-HOST.

### The pooled comparison, which the rule names literally

| group | n | n OVERLAP | n CLEAR | CLEAR p50 | OVERLAP p50 | difference | 95 % CI |
|---|---|---|---|---|---|---|---|
| KV-HOST | 28858 | 12474 | 16384 | 0.1550 | 0.2254 | +0.0704 | [+0.0682, +0.0727] |
| KV-GPU control | 3419 | 755 | 2664 | 0.1897 | 0.4293 | +0.2396 | [+0.1860, +0.3660] |

The pooled control difference (+0.2396 s) is larger than the pooled host difference (+0.0704 s), so hypothesis (ii) fails on the literal rule too — but for a reason worth stating: one control cell, `E10B_KVGPU_k4_r0_N3_L50`, is a **re-prefill collapse** cell whose overlap difference is +1.59 s, and it drags the pooled control up. Both readings reach the same verdict; the cell-matched table above is the one that is like-for-like.

### The regression

`ttft_s ~ 1 + overlap + n_concurrent + cached_ktokens + new_ktokens + load_fraction, OLS on every KV-HOST k > 0 episodic request not overlapping a cold recall; CIs from 200 bootstrap refits (requests resampled)`

| term | coefficient | 95 % CI |
|---|---|---|
| `intercept` | +0.07758 | [+0.07360, +0.08191] |
| `overlap` | -0.05992 | [-0.07881, -0.04015] |
| `n_concurrent` | +0.18832 | [+0.17128, +0.20414] |
| `cached_ktokens` | -0.00001 | [-0.00084, +0.00080] |
| `new_ktokens` | -0.27865 | [-0.33379, -0.21472] |
| `load_fraction` | +0.38050 | [+0.36412, +0.39726] |

n = 28858, R2 = 0.601.

Read it carefully. The **pre-registered expectation was that the gap scales with the overlapping request's `cached_tokens`** — the proxy for KV bytes reloaded, and the quantity the host-residency hypothesis needs. Its coefficient is **-0.000007 s per thousand cached tokens, with a CI spanning zero**: over a range of roughly 0 to 28,000 cached tokens, reloaded KV volume predicts nothing. What does predict is the **number** of recall requests concurrently in flight (+0.188 s each) and the load level (+0.380 s per unit of offered load). With `n_concurrent` in the model the binary overlap indicator turns negative, which is the usual collinearity between an indicator and its own count and is why the cell-matched medians, not the regression, carry the verdict.

## 5. Step 3 — the pre-registered decision

| hypothesis | rule | result | supported? |
|---|---|---|---|
| (i) mode cost | the k = 0 KV-HOST minus KV-GPU median difference exceeds the noise floor with CI excluding 0 | +0.0414 s (CI +0.0384, +0.0456) and +0.0355 s (CI +0.0290, +0.0405) at N = 1, against a 0.0165 s floor | **YES** |
| (ii) overlap cost | the OVERLAP minus CLEAR difference in KV-HOST cells has CI excluding 0 **and exceeds** the same difference in the KV-GPU control | CI excludes 0 (+0.0704 s pooled), but the control is +0.2396 s pooled and +0.0574 s cell-matched against the host's +0.0526 s | **NO** |

**Verdict: (i) mode cost only.** The slowdown is the cost of the connector being enabled, not the cost of a session being resident. The clearest single statement of it: StudyE10b's KV-HOST ladder at k = 0 has **no warm session and no recall request of any kind in the system**, and it is still 0.041 s per request slower than the identical KV-GPU ladder.

This **contradicts StudySIM1's own attribution**. SIM1 named the missing mechanism as "a resident long-context recall request lengthens every step it shares". Two things in the data above rule that out as the main effect: the slowdown is present with zero resident sessions, and reloaded KV volume (`cached_tokens`) predicts nothing. SIM1's attribution was made without the k = 0 KV-HOST cells, which are in none of its gate cells. It is corrected here.

## 6. CLAUDE.md mechanism verification (Steps 1-5)

### Step 1 — the causal chain

If enabling vLLM's host-offload KV connector costs a fixed amount of request-handling time per request, independent of whether any session is resident (FORMULATION.md places host offload in the placement tier, and StudyRH5 measured its per-reload cost but never its fixed cost), then every request in a KV-HOST configuration is delivered later than the same request in the identical KV-GPU configuration by that amount; the shift appears in the **median**, not only in the tail, because it is paid by every request and not only by the ones that queue behind something; a simulator that charges the per-reload cost but not the fixed cost therefore reproduces the KV-GPU and cold cells and runs systematically optimistic in every KV-HOST cell; and adding the fixed cost moves the simulated KV-HOST p50 towards the measured p50 without touching any KV-GPU or cold cell.

### Step 2 — instantiate each link

| causal link | implementing quantity | value / range in this run | varies as expected? | evidence |
|---|---|---|---|---|
| connector enabled -> fixed per-request cost | the KV-HOST minus KV-GPU episodic TTFT p50 at k = 0, r = 0 | +0.0414 s at 25 %, +0.0355 s at 50 %, +0.0170 s at 90 % (N = 1) | YES — non-zero, CI excludes 0 at the two low levels, above the 0.0165 s drift floor | section 3 |
| cost is paid by every request -> it moves the median | the p50, not only the p99 | measured p50 rises 0.1301 -> 0.1715 s with zero warm sessions | YES | section 3 |
| cost is non-blocking -> it is not amplified by queueing | the difference as a function of load | +0.0414, +0.0355, -0.0006, +0.0170 s at 25/50/75/90 % | YES, and in the direction that rules engine occupancy out | section 3 |
| not paid in GPU mode -> KV-GPU cells unchanged | `Engine.host_mode_cost_s` applies only when `kv_mode == HOST` | 4 of 4 KV-GPU and cold cells bit-identical with the option ON | YES | control 1, section 8 |
| modelled cost -> simulated KV-HOST p50 moves | `sim_p50_s` in the gate's KV-HOST cells | 0.1440 -> 0.1825 s (k = 8 and k = 16 at 25 %), 0.1455 -> 0.1840 s (C4 at 10 %) | YES | section 7 |
| **reloaded KV volume -> extra cost** (the hypothesis (ii) link) | regression coefficient on `cached_ktokens` | **-0.000007 s per 1,000 tokens, CI [-0.00084, +0.00080]** | **NO — CONSTANT / ABSENT** | section 4 |

The last row is an **ABSENT link**, and it is reported as such: hypothesis (ii) has no implementing quantity that varies, which is exactly why its option was not added. The five links of hypothesis (i) are all present and vary as the claim requires, so the Step-4 option implements (i) only.

### Step 3 — one representative unit

One episodic request in `KVHOST-k8`, N = 1, 25 % load, option ON:

```
request      ep417   episodic, N = 1
arrival_s    138.4210   (Poisson draw, arrival seed 2)
frontend_s     0.0678   = 0.134 s measured TTFT at concurrency 1 minus 378 / 5,708 tok/s
host mode cost +0.0385  CHARGED (kv_mode == HOST); non-blocking, so it shifts visibility only
visible_s    138.5273   = arrival + frontend + mode cost
compute      378 tokens at 5,708 tok/s = 0.0662 s of engine time
step budget  8,192 tokens; the request fits in one step; cap 0 (P0), so no cap applies
KV           GPU 62,944 tokens, 8 warm sessions resident on HOST, 0 on GPU -> no eviction
bound by     neither budget: the step had room; the request waited only for visibility
done_s       138.6055
TTFT         0.1845 s  = 0.0678 frontend + 0.0385 mode cost + 0.0662 compute + 0.0120 step
outcome      within the 0.45 s N = 1 budget
```

The arithmetic is checkable by hand and the mode cost appears as one addend, which is the point: it is charged once per request and nowhere else.

### Step 4 — negative controls

Three, in section 8. Two pass; the third fails on its stated criterion and the failure is reported rather than redefined.

### Step 5 — the alternative explanation

The same headline (KV-HOST cells are slower) would be produced by **(a)** a fixed connector cost per request [the claimed mechanism], **(b)** a cost proportional to reloaded KV volume [hypothesis (ii) / SIM1's original attribution], or **(c)** between-study drift, if the KV-HOST cells happened to run at a different time from the KV-GPU cells. The data separate all three. (b) is excluded because the effect is present at k = 0, with nothing resident to reload, and because `cached_tokens` has a zero coefficient. (c) is excluded because the KV-GPU and KV-HOST k = 0 ladders are cells of **one** StudyE10b run, and the between-study drift that does exist is measured separately and is smaller (0.0165 s) than the effect (0.0414 s) at N = 1. At N = 3 the drift floor is **larger** than the effect, and the report says so and does not use those cells.

## 7. Step 5 — the gate, run once

SIM1's calibration gate, unchanged: the same 29 p99 cells, 16 ladders and 8 p50 cells, the same 5 arrival seeds, the same +/-25 % bar and 80 % thresholds, the same collapse rule. The option's value (0.0385 s) comes only from Step 1's held-out cells; no gate cell was used to choose it and no other SIM1 constant was touched.

| | p99 cells | capacity ladders | verdict |
|---|---|---|---|
| option OFF (reproduces SIM1) | 18 / 29 (62 %) | 10 / 16 (62 %) | FAIL |
| **option ON — (i) host mode cost** | **20 / 29 (69 %)** | **11 / 16 (69 %)** | **FAIL** |

**Ablation.** The specification asks for the gate with only (i) ON and with only (ii) ON. There is no (ii): Step 3 did not support it, and the specification's Step 4 adds only the supported effects, so no overlap-cost option exists. "(i) only" and "both ON" are the same configuration, and it is the row above.

### Every cell, before and after

| condition | N | load | measured p99 | OFF | ratio | | ON | ratio | |
|---|---|---|---|---|---|---|---|---|---|
| C0 | 1 | 10 % | 0.216 | 0.228 | 1.06 | OK | 0.228 | 1.06 | OK |
| C0 | 1 | 20 % | 0.276 | 0.279 | 1.01 | OK | 0.279 | 1.01 | OK |
| C0 | 1 | 25 % | 0.271 | 0.301 | 1.11 | OK | 0.301 | 1.11 | OK |
| C0 | 1 | 30 % | 0.294 | 0.326 | 1.11 | OK | 0.326 | 1.11 | OK |
| C0 | 1 | 40 % | 0.383 | 0.400 | 1.04 | OK | 0.400 | 1.04 | OK |
| C0 | 1 | 50 % | 0.452 | 0.484 | 1.07 | OK | 0.484 | 1.07 | OK |
| C0 | 3 | 10 % | 0.360 | 0.457 | 1.27 | X | 0.457 | 1.27 | X |
| C0 | 3 | 25 % | 0.510 | 0.629 | 1.23 | OK | 0.629 | 1.23 | OK |
| C0 | 3 | 50 % | 1.058 | 1.061 | 1.00 | OK | 1.061 | 1.00 | OK |
| C1-r05 | 1 | 10 % | 2.646 | 3.857 | 1.46 | X | 3.857 | 1.46 | X |
| C1-r05 | 1 | 25 % | 2.942 | 2.799 | 0.95 | OK | 2.799 | 0.95 | OK |
| C1-r05 | 3 | 25 % | 2.708 | 3.404 | 1.26 | X | 3.404 | 1.26 | X |
| C1-r05 | 3 | 50 % | 4.472 | 4.505 | 1.01 | OK | 4.505 | 1.01 | OK |
| C1-r10 | 1 | 25 % | 8.521 | 6.716 | 0.79 | OK | 6.716 | 0.79 | OK |
| C1-r10 | 3 | 25 % | 7.129 | 7.119 | 1.00 | OK | 7.119 | 1.00 | OK |
| C1-r10 | 3 | 50 % | 8.619 | 9.193 | 1.07 | OK | 9.193 | 1.07 | OK |
| C4 | 1 | 10 % | 4.710 | 8.485 | 1.80 | X | 8.523 | 1.81 | X |
| C4 | 1 | 25 % | 11.440 | 7.058 | 0.62 | X | 7.096 | 0.62 | X |
| C4 | 3 | 25 % | 10.230 | 7.213 | 0.71 | X | 7.251 | 0.71 | X |
| KVGPU-k4 | 1 | 25 % | 0.536 | 0.339 | 0.63 | X | 0.339 | 0.63 | X |
| KVGPU-k4 | 3 | 25 % | 0.705 | 0.640 | 0.91 | OK | 0.640 | 0.91 | OK |
| KVGPU-k8 | 1 | 25 % | 192.800 | 138.737 | 0.72 | OK | 138.737 | 0.72 | OK |
| KVGPU-k8 | 3 | 25 % | 183.300 | 132.441 | 0.72 | OK | 132.441 | 0.72 | OK |
| KVHOST-k16 | 1 | 10 % | 0.440 | 0.309 | 0.70 | X | 0.348 | 0.79 | OK |
| KVHOST-k16 | 1 | 20 % | 0.478 | 0.351 | 0.73 | X | 0.390 | 0.82 | OK |
| KVHOST-k16 | 3 | 25 % | 0.594 | 0.795 | 1.34 | X | 0.833 | 1.40 | X |
| KVHOST-k8 | 1 | 25 % | 0.339 | 0.382 | 1.13 | OK | 0.421 | 1.24 | OK |
| KVHOST-k8 | 1 | 40 % | 0.478 | 0.441 | 0.92 | OK | 0.479 | 1.00 | OK |
| KVHOST-k8 | 3 | 25 % | 0.516 | 0.685 | 1.33 | X | 0.724 | 1.40 | X |

### Capacity ladders

| condition | N | measured | OFF | | ON | |
|---|---|---|---|---|---|---|
| C0 | 1 | 40 % | 40 % | OK | 40 % | OK |
| C0 | 3 | 50 % | 50 % | OK | 50 % | OK |
| C1-r05 | 1 | below ladder | below ladder | OK | below ladder | OK |
| C1-r05 | 3 | below ladder | below ladder | OK | below ladder | OK |
| C1-r10 | 1 | below ladder | below ladder | OK | below ladder | OK |
| C1-r10 | 3 | below ladder | below ladder | OK | below ladder | OK |
| C4 | 1 | below ladder | below ladder | OK | below ladder | OK |
| C4 | 3 | below ladder | below ladder | OK | below ladder | OK |
| KVGPU-k4 | 1 | below ladder | 40 % | X | 40 % | X |
| KVGPU-k4 | 3 | 25 % | 50 % | X | 50 % | X |
| KVGPU-k8 | 1 | below ladder | below ladder | OK | below ladder | OK |
| KVGPU-k8 | 3 | below ladder | below ladder | OK | below ladder | OK |
| KVHOST-k16 | 1 | 10 % | 30 % | X | 30 % | X |
| KVHOST-k16 | 3 | 25 % | 35 % | X | 35 % | X |
| KVHOST-k8 | 1 | 30 % | 40 % | X | 30 % | OK |
| KVHOST-k8 | 3 | 25 % | 35 % | X | 35 % | X |

"below ladder" means the lowest level tested already missed the budget — StudySIM1's and StudyE10c's own convention.

### The p50 table — where the mechanism shows

| condition | N | load | measured p50 | OFF | ON | measured minus ON |
|---|---|---|---|---|---|---|
| C0 | 1 | 10 % | 0.147 | 0.144 | 0.144 | +0.0030 |
| C0 | 1 | 25 % | 0.140 | 0.144 | 0.144 | -0.0040 |
| C0 | 1 | 40 % | 0.150 | 0.144 | 0.144 | +0.0060 |
| C0 | 3 | 25 % | 0.280 | 0.264 | 0.264 | +0.0162 |
| C1-r05 | 1 | 10 % | 0.147 | 0.144 | 0.144 | +0.0030 |
| C4 | 1 | 10 % | 0.211 | 0.146 | 0.184 | +0.0270 |
| KVHOST-k16 | 1 | 25 % | 0.180 | 0.144 | 0.183 | -0.0025 |
| KVHOST-k8 | 1 | 25 % | 0.200 | 0.144 | 0.183 | +0.0175 |

This is the table the study was run to move. StudySIM1's failure diagnosis was that the measured episodic p50 rises 0.04-0.06 s under KV-HOST load while the simulated p50 did not move at all. With the mode cost ON it moves: KV-HOST k = 16 at 25 % now matches to 0.0025 s (0.1825 against 0.180), k = 8 at 25 % is 0.0175 s short, and C4 at 10 % is 0.027 s short. The five cells with no host offload are untouched, as they must be.

## 8. Negative controls

**Control 1 — options ON, KV mode GPU: PASS.** Control 1: with the option ON but the KV mode GPU, every KV-GPU and cold cell must be unchanged - the cost is defined to be paid only when the host-offload connector is enabled.

| cell | OFF | ON | identical? |
|---|---|---|---|
| C0 N1 25 % | 0.300500 | 0.300500 | yes |
| C1-r05 N1 10 % | 3.856940 | 3.856940 | yes |
| KVGPU-k4 N1 25 % | 0.338973 | 0.338973 | yes |
| C1-r10 N3 25 % | 7.118641 | 7.118641 | yes |

**Control 2 — the cost set to 0 reproduces StudySIM1: PASS.** The OFF run above returns 18 / 29 p99 cells and 10 / 16 ladders, which is StudySIM1's committed result cell for cell.

**Control 3 — the cost forced onto a KV-GPU cell must make it disagree: FAILED as specified.**

| cell | quantity | measured | OFF | forced ON | ratio OFF | ratio forced | still agrees? |
|---|---|---|---|---|---|---|---|
| C0 N1 25 % | p99 | 0.271 | 0.3005 | 0.3390 | 1.109 | 1.251 | **no** |
| C0 N1 40 % | p99 | 0.383 | 0.3996 | 0.4381 | 1.043 | 1.144 | yes |
| C0 N1 25 % | p50 | 0.140 | 0.1440 | 0.1825 | 1.029 | 1.304 | **no** |
| C0 N1 40 % | p50 | 0.150 | 0.1440 | 0.1825 | 0.960 | 1.217 | yes |

The control's criterion was that **every** forced cell stops agreeing. One of the two p99 cells flips (C0 at 25 %: ratio 1.109 -> 1.251, outside the band) and the other does not (C0 at 40 %: 1.043 -> 1.144, still inside). So the control **fails as written**, and that verdict stands.

What the control does establish, and what it does not: the forced cost moves **both** cells away from their measurement, so it is not a quantity that improves whatever it touches. The reason it does not flip both is a property of the bar, not of the cost — +/-25 % of a 0.383 s p99 is +/-0.096 s, and the cost is 0.0385 s, so it cannot by itself leave a band that wide. On the p50, the quantity the cost acts on directly, the forced cells go to ratios 1.304 and 1.217 against 1.029 and 0.960. The p50 rows were added after the control returned FAIL and are evidence, not a replacement criterion.

## 9. The gate still fails — the stopping condition

The specification says to stop and ask if the gate still fails, to report which cells, and not to iterate. It does fail, at 69 % and 69 % against an 80 % bar. Nine p99 cells and five ladders still disagree:

| condition | N | load | measured | simulated | ratio | what kind of disagreement |
|---|---|---|---|---|---|---|
| C0 | 3 | 10 % | 0.360 | 0.457 | 1.27 | N = 3 over-queueing (section 10) |
| C1-r05 | 1 | 10 % | 2.646 | 3.857 | 1.46 | cold-recall tail too long at 10 %; the hold is modelled, its length is not calibrated there |
| C1-r05 | 3 | 25 % | 2.708 | 3.404 | 1.26 | N = 3 over-queueing |
| C4 | 1 | 10 % | 4.710 | 8.523 | 1.81 | too SLOW: the hold and the mode cost compound |
| C4 | 1 | 25 % | 11.440 | 7.096 | 0.62 | too FAST: the measured 11.44 s cell is saturating and the model does not saturate |
| C4 | 3 | 25 % | 10.230 | 7.251 | 0.71 | too FAST, the same cell at N = 3 |
| KVGPU-k4 | 1 | 25 % | 0.536 | 0.339 | 0.63 | too FAST: the warm-miss lookup returns 0 below 1x KV footprint, so nothing re-prefills at k = 4 |
| KVHOST-k16 | 3 | 25 % | 0.594 | 0.833 | 1.40 | N = 3 over-queueing on top of the warm load |
| KVHOST-k8 | 3 | 25 % | 0.516 | 0.724 | 1.40 | N = 3 over-queueing on top of the warm load |

| ladder | N | measured capacity | simulated | direction |
|---|---|---|---|---|
| KVGPU-k4 | 1 | below ladder | 40 % | optimistic |
| KVGPU-k4 | 3 | 25 % | 50 % | optimistic |
| KVHOST-k16 | 1 | 10 % | 30 % | optimistic |
| KVHOST-k16 | 3 | 25 % | 35 % | optimistic |
| KVHOST-k8 | 3 | 25 % | 35 % | optimistic |

Two groups, and they are different problems. **Four of the five remaining ladder disagreements and three of the nine cell disagreements are N = 3**, where the model over-queues (section 10). The rest are KV-GPU k = 4 (the warm-miss lookup returns 0 below 1x KV footprint, so the model draws no miss at k = 4 while the measurement saw one of 106) and C4 at 25 % (the measurement is in saturation at 11.44 s and the model is not).

**No parameter was tuned, and the gate was run once with the option ON, as pre-registered.**

## 10. The N = 3 over-queueing gap, reported separately

StudySIM1 reported a second, smaller gap: at N = 3 the simulated p99 runs above the measurement at the low and middle levels while the p50 agrees to 6 %. It is unchanged by this study and is **not** addressed here. With the option ON the N = 3 ratios are:

| condition | load | ratio |
|---|---|---|
| C0 | 10 % | 1.27 |
| C0 | 25 % | 1.23 |
| C0 | 50 % | 1.00 |
| C1-r05 | 25 % | 1.26 |
| C1-r05 | 50 % | 1.01 |
| C1-r10 | 25 % | 1.00 |
| C1-r10 | 50 % | 1.07 |
| C4 | 25 % | 0.71 |
| KVGPU-k4 | 25 % | 0.91 |
| KVGPU-k8 | 25 % | 0.72 |
| KVHOST-k16 | 25 % | 1.40 |
| KVHOST-k8 | 25 % | 1.40 |

## 11. What this implies for the HOST-WARM tier

**Enabling host offload is a fleet-wide cost, not a per-session one.** That is the practical finding, and it changes how the HOST-WARM tier should be priced in any policy that chooses it.

| component | who pays | size | source |
|---|---|---|---|
| connector enabled | **every request on the replica**, including requests of sessions that are not offloaded, and requests in a replica with no warm session at all | +0.0385 s per request (0.0414 s at 25 % load, 0.0355 s at 50 %) | this study, Step 1 |
| a host reload | the request whose prefix is reloaded | 0.031 s at 11k tokens, 0.117 s at 28k | StudyRH5 Part A |
| a recall request in flight | episodic requests whose service overlaps it | +0.05 to +0.07 s, **the same in KV-GPU and KV-HOST** | this study, Step 2 |

The consequences for the tier:

* The decision to enable host offload is a **replica-level** decision, not a per-session one. A policy that offloads one session has already charged every other request on that replica.
* The break-even is a ratio, not a threshold: at F episodic requests per second, enabling the connector costs 0.0385 x F seconds of added delivery latency per second of operation, against the re-prefill it avoids. At StudyE10b's 25 % N = 1 load (3.775 req/s) that is 0.145 s of added latency per second, against a 12,645-token re-prefill at 5,827 tok/s = 2.17 s avoided per collapse event. Host offload pays for itself only where the collapse rate is above roughly one event per 15 s of operation at that load.
* **StudyE9d's delivery curves make this concrete on the episodic side.** 0.0385 s added to every delivered score is small against the d* values StudyE9d measured (2.54 s for 32B N = 1 at 0.5 s cadence), so the mode cost does not by itself change an episodic placement decision. It changes capacity: it is 27 % of the N = 1 service time, and the KV-HOST k = 8 ladder is exactly what it moved in the gate (simulated 40 % -> 30 %, matching the measured 30 %).
* The honest limit: the mode cost was measured at 10-50 % load and **vanishes at 75-90 %**, and nothing here reproduces that. Any claim about host offload at saturation is outside what this study measured.

## 12. Results consistency check

**1. Cross-check against committed measurements.**

| quantity | this run | prior run | source of prior | ratio | agree? |
|---|---|---|---|---|---|
| episodic TTFT p50, KV-GPU k0 r0 N1 25 % | 0.1301 s | 0.14-0.15 s | StudyE10c C0 N1 p50 | 0.90 | AGREE |
| episodic TTFT p99, KV-GPU k0 r0 N1 25 % | 0.2859 s | 0.286 s | StudyE10b's own report | 1.00 | AGREE |
| KV-HOST k8 N1 25 % measured p50 | 0.200 s | 0.20 s | StudyE10b report, SIM1's `REF_P50` | 1.00 | AGREE |
| simulated C0 N1 25 % p99, option OFF | 0.3005 s | 0.3005 s | StudySIM1 committed calibration | 1.00 | AGREE |
| simulated KV-GPU k8 N1 25 % p99 | 138.737 s | 125.257 s | StudySIM1 committed (superseded, section 1) | 1.11 | AGREE, and explained |
| host reload visible cost at 11k | not re-measured | 0.031 s | StudyRH5 Part A | - | used unchanged |

No disagreement above 2x.

**2. Physical plausibility.** The mode cost is 0.0385 s per request. StudyD7b's whole measured TTFT at concurrency 1 is 0.134 s, of which 0.066 s is compute at 5,708 tok/s, leaving 0.068 s of request handling. The mode cost is 57 % of that handling time and 0 % of the compute time, which is consistent with a connector on the handling path and inconsistent with it being GPU work. No rate implied anywhere here exceeds a committed curve.

**3. Distribution sanity.** Every Step-1 and Step-2 difference carries a 2,000-resample bootstrap CI and every percentile table carries p10/p50/p90/p99 and n. The difference is *not* constant across cells (it runs +0.0414 to -0.0006 s across the N = 1 ladder), which is the opposite of the short-circuit pattern this check exists to catch, and the variation is itself the section-3 finding. Gate cells report the 5-seed median with min and max.

**4. Definition audit.**

| object | definition used here | prior definition | match? |
|---|---|---|---|
| episodic TTFT | `ttft_s` from the SCHEDULED arrival = `t_sched + dispatch_late_s` | StudyD7 / E10b / E10c / E10e, identical | yes |
| a cell's load level | `frac` x the measured peak req/s (15.10 at N = 1, 5.38 at N = 3) | StudyD7b peaks, as E10b used | yes |
| OVERLAP | episodic `[submit, submit + ttft]` intersects a recall `[t_submit, t_end]` | new in this study; defined here and in the script | n/a, new |
| warm / cold | `cold_recall` is a whole-history prefill; `recall_append` / `escalation` run over a cached prefix | StudyE10b's own kinds, unchanged | yes |
| capacity | highest ladder level whose episodic p99 meets the budget | StudyD7 / E10b / E10c | yes |

Caching is a stated parameter throughout: every number here comes from StudyE10b / E10c / E10e runs whose prefix-caching configuration is recorded in their own `run_meta`, and warm and cold requests are never pooled.

**5. Claim linkage.** The headline bears on the placement tier of FORMULATION.md: the HOST-WARM tier carries a **fixed, replica-wide** cost that the formulation's per-session accounting does not contain. It supports the claim that context inertia has a physical component, and it **weakens** any version of that claim in which the physical component is purely per-session and proportional to context length. Nothing measured here is scoped out by FORMULATION.md: this is same-model KV between GPU and host on one replica, not cross-architecture KV transfer.

**6. Proxy validity.** One proxy is used and one is tested and rejected. `cached_tokens` is used as a proxy for KV bytes reloaded; it is the right proxy (StudyRH5's 262,144 B per token makes it exact up to block rounding), and it is the quantity whose coefficient is zero — so the rejection is a rejection of the mechanism, not of the proxy. The OVERLAP label is a proxy for "this request shared the engine with recall work", and it is imperfect at the edges: a request whose TTFT is long *because* it was held overlaps more recall intervals than one that was not, so OVERLAP and slowness are partly mechanically linked. That is why the verdict reads the **cell-matched host-versus-control difference**, where that link is present on both sides and cancels, rather than the raw OVERLAP-minus-CLEAR gap.

## 13. Files

| file | what |
|---|---|
| `experiments/orchestration/sim/sim1b_hosttax.py` | Steps 0-3 (default) and Step 5 (`--gate`) |
| `experiments/orchestration/sim/engine.py` | the `host_mode_cost_s` option, **default 0.0 = OFF** |
| `experiments/orchestration/sim/calibrate.py` | the option plumbed through `run_cell`; the warm-miss draw keyed on (cell, arrival seed) |
| `results/orchestration/sim1b/sim1b_steps.json` | Steps 0-3, every number |
| `results/orchestration/sim1b/sim1b_step1_mode_cost.csv` | the held-out mode-cost table |
| `results/orchestration/sim1b/sim1b_step2_overlap.csv` | the per-cell overlap table |
| `results/orchestration/sim1b/sim1b_gate.json` | the gate OFF and ON, with the controls |
| `results/orchestration/sim1b/sim1b_gate_cells.csv` | the before/after cell table |

