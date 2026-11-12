# StudyE10e-partial-prefill: does capping a long prefill's per-step tokens remove the cold-recall interference?

E-id: StudyE10e-partial-prefill (`research/EXPERIMENTS.md`, pre-registered 2026-11-12, design decisions by the user 2026-11-12). Host: h100nvl **GPU 2**, exclusive.

## 0. Question and design (recorded before running)

**Question.** StudyE10d found that the unit holding episodic requests behind a cold K1 RICH recall is the LM prefill of its ~12.6k tokens. vLLM 0.31.0 schedules RUNNING requests first, and `long_prefill_token_threshold` defaults to 0 (no cap), so a running long prefill takes each step's whole token budget until it finishes. Neither priority scheduling nor a 2,048-token step budget changed that (E10c). Does vLLM's long-prefill cap restore episodic capacity under cold recall, and at what cost to the recall?

**Flag check (vLLM 0.31.0, before any run).** Supported options:

| flag | in 0.31.0? | default | applies to | source |
|---|---|---|---|---|
| `--long-prefill-token-threshold N` | **yes** | 0 (off) | V1 scheduler with chunked prefill, RUNNING requests (l. 679) and WAITING requests (l. 1110) | `vllm/config/scheduler.py` l. 80–85; `vllm/engine/arg_utils.py` l. 592, 1701, 2565; `vllm/v1/core/sched/scheduler.py` l. 611–680, 1110; `vllm serve --help=all` |
| `--scheduling-policy {fcfs,priority}` | yes | fcfs | V1 scheduler | `vllm serve --help=all` |
| `--long-prefill-token-threshold-adaptive` | yes (**not used**) | off | floors the cap at max_num_batched_tokens ÷ (running + waiting) | `config/scheduler.py` l. 87–91; `scheduler.py` l. 621–626 |
| `--max-num-partial-prefills` | **NO**, unsupported | — | — | absent from `vllm serve --help=all`, `EngineArgs` (`arg_utils.py`), `SchedulerConfig` and the V1 scheduler |
| `--max-long-partial-prefills` | **NO**, unsupported | — | — | as above |

What the source shows about the unsupported counters and the cap:
- The V1 scheduler has no limit on how many partial prefills run at once; only the token budget limits them.
- The user dropped the two counters from P1 and P2 and declined the adaptive option, whose floor weakens the cap when few requests wait, which is the C1 case.
- **The cap is skipped when only one request is in the system** (`scheduler.py` l. 611–619: "When it is the only request there is nobody to starve, so let it use the whole budget").

**Harness.** These are imported unchanged:
- `study_e10b_mixed.py`: `run_cell`, `Episodic`, the D7 open loop, RH7 warm sessions, the exclusivity monitor ignoring `<defunct>`, VOID on overlap, the 30-s discard, 240-s window and 300-s drain cap.
- `study_e10d_blocking.py`: the cold V1 / V3 bodies with `request_id`, `--enable-log-requests`, the millisecond logging config, and the server-log phase times.

Only the engine flags change.

**Configs:**

| config | flags | expected in the server log's non-default args |
|---|---|---|
| P0 | E0 defaults (chunked prefill on, max_num_batched_tokens 8192, fcfs) | no threshold, fcfs |
| P1 | `--long-prefill-token-threshold 1024` | 1024, fcfs |
| P2 | `--long-prefill-token-threshold 512` | 512, fcfs |
| P3 | P1 + `--scheduling-policy priority` (episodic 0, warm 1, cold 2, as E10c) | 1024, priority |

The run STOPs if a server's log disagrees.

**Conditions and ladder:**
- **Conditions:**
  - C0: KV-GPU, no recall;
  - C1: KV-GPU, cold r = 0.05 req/s;
  - C4: KV-HOST k = 8 warm sessions + cold r = 0.1.
- **Ladder:** episodic N = 1, budget p99 ≤ 0.45 s, levels 10 / 20 / 25 / 30 / 40 % of 15.1 req/s. Bottom-up per (config, condition), stopping at the first failure.
  - P0 runs the full C0 ladder.
  - P1–P3 run C0 at 25 % and 40 % only (user decision).
- **Cold request:** V1 (PNG video, = E10c / E10d) throughout. V3 (E10d's token-matched text) at C1 10 % and 25 % in every config.
- **Seeds:** E10c's (level-index map, cold seed 1000 + index).
- **Other:** fresh server per cell; stop before a new cell once 6 h have elapsed.

**Control gate.**
- P0 C0 25 % must reproduce E10c E0 (0.279 s).
- P0 C1 10 % must reproduce E10c E0 (2.739 s) and E10d V1 E0 (2.974 s).
- Both must agree within 2×, else STOP.

**Pre-registered decision.**
- A config **removes the interference** iff its C1 capacity is within one ladder level of its own C0 capacity.
- Its cost is reported as cold TTFT p50 / p99 vs P0 and any C0 capacity loss.
- If no config removes it, the interference is not removable by vLLM's documented scheduling controls on this stack.

**Estimate.** 27–51 cells at about 6.2 min each, 2.8–5.3 h.

## 1. Mechanism verification (recorded BEFORE the sweep)

**Step 1, causal chain.**
- FORMULATION's shared-replica cost asks whether recall can share a replica with episodic scoring. E10b / E10c found it cannot, because each cold recall holds episodic requests until its first token. E10d located the hold in the LM prefill, by this chain:
  - the scheduler serves RUNNING requests first;
  - a running long prefill is given `min(remaining tokens, token budget)` each step, which is 8,192 at E0 and 2,048 at E2;
  - an episodic request arriving meanwhile can only be scheduled with whatever budget is left, which is none while the prefill has more than budget-many tokens left;
  - so it waits for consecutive full steps until the prefill completes.
- The claim under test: setting `long_prefill_token_threshold` = T caps the running prefill at T tokens per step. That leaves budget − T tokens (7,168 or 7,680) for waiting requests in the same step, so an episodic request (378 tokens) is scheduled at the next step boundary instead of after the whole prefill. Episodic p99 then falls under the budget, and C1 capacity returns toward C0.
- The cost: the cold prefill is split into about 12.6k ÷ T steps (13 at T 1024, 25 at T 512), each with fixed per-step overhead, so cold TTFT should rise.

**Step 2, instantiate each link.**

| link | implementing quantity | value / range in this run | varies as needed? | evidence |
|---|---|---|---|---|
| per-step cap on a long prefill | `long_prefill_token_threshold` | 0 (P0), 1024 (P1, P3), 512 (P2) | yes, by config | server log non-default args, checked per server |
| cap active | number of requests in the system > 1 (scheduler.py l. 616–619) | episodic arrivals 1.5–6.0 req/s, warm sessions (C4) | yes, by level and condition | 1-s /metrics running / waiting timeline |
| long prefill present | cold K1 / V3 prompt, 11.3–12.6k tokens | r 0.05 (C1) / 0.1 (C4) cold req/s; none at C0 | yes, by condition | per-request `prompt_tokens` |
| episodic hold | episodic p99, slow fraction inside cold windows, release − cold first token | measured | to be measured | rows + server log |
| cost to recall | cold TTFT p50 / p99; append / escalation TTFT | measured | to be measured | rows |

No link is ABSENT or CONSTANT.

**Prediction recorded before the sweep: the "only request" exemption.**
- The cap is not applied when the cold request is the only request in the system.
- At 10 % episodic load (1.5 req/s, ~0.15 s service) the cold request is often alone when scheduled. It then gets a full 8,192-token step: about 1.4 s at E10d's 5.8k tok/s prefill rate, plus the ≈ 0.2-s vision-encoder pass, which is always one step.
- An episodic request arriving during such a step waits for it to end, and steps are not preemptible.
- **So the cap can shorten the hold only from the step after another request appears.** The pre-registered reading is therefore not expected to be a clean "fix":
  - a residual hold of up to one full alone-step is predicted;
  - a lower episodic arrival rate (10 %) may *exempt more* cold steps than a higher one.
- The release-timing analysis and the cold-alone fraction (from the timeline) will show whether this happens.

**Step 3, trace one unit.** For one cold request per config (C1 V1 10 %), the report gives:
- send, 'Received request', 'Added request' and first-token times;
- the episodic requests submitted around it, with TTFT and release relative to the cold first token (E10c §6 / E10d §4).

The per-step token allocation is not logged by vLLM 0.31.0 (no per-step scheduler log at INFO). The request-level trace and the 1-s running / waiting timeline are the instrumentation available. That is the same level as E10d.

**Step 4, negative control.**
- P0 is the mechanism switched off (threshold 0). It must reproduce E10c / E10d's C1 hold.
- C0 in every config is the no-long-prefill null. A cap of 512 / 1024 tokens is above every 378-token episodic prompt, so C0 must not move.
- V3 at C1 removes the vision encoder (a single unchunkable step), isolating the cap's effect on the LM prefill alone.

**Step 5, alternative explanations.**
- **(i) Lower load instead of a removed hold.** A capped config could reach C1 capacity because the cold prefill now runs slower and overlaps fewer episodic arrivals with full-budget steps, not because waiting requests are co-scheduled.
  - Distinguishing evidence: with co-scheduling, slow episodic requests inside cold windows disappear, and those that remain are not released at the cold first token.
- **(ii) A residual hold from the vision encoder or from "alone" steps.** Either could keep p99 above budget although the cap works.
  - Distinguishing evidence: V3 (no encoder), and where the remaining slow requests sit relative to the cold request's engine arrival (early in the window = alone or encoder step).
- **(iii) Priority (P3) changing waiting-queue order.** E10c showed that alone does nothing; P3 vs P1 isolates it.

## 2. Run (2026-11-12 10:59 → 13:49)

- **Size:** 27 cells in 2 h 50 min (≈ 6.2 min per cell), inside the 2.8–5.3 h estimate. Every capped ladder stopped at its first level, so the run took the short path.
- **Exclusivity:** 360 monitor samples; foreign process on GPU 2 in 0, our processes outside the job in 0. **Not VOID.**
- **Flags verified from every server log** (27 / 27):

  | config | `long_prefill_token_threshold` | `scheduling_policy` |
  |---|---|---|
  | P0 | 0 | fcfs |
  | P1 | 1024 | fcfs |
  | P2 | 512 | fcfs |
  | P3 | 1024 | priority |

  All servers ran with chunked prefill on and `max_num_batched_tokens` 8192.
- **Control gate:** PASS.

  | P0 cell | p99 | reference | ratio |
  |---|---|---|---|
  | C0 25 % | 0.271 s | E10c 0.279 s | 0.97 |
  | C1 10 % | 2.646 s | E10c 2.739 s | 0.97 |
  | C1 10 % | 2.646 s | E10d V1 2.974 s | 0.89 |

- **Errors:** every cold prompt was token-exact, and every cold request was found in the server log. Every cell had 0 episodic errors, 0 preemptions, 0 unfinished at the drain cap and 0 warm misses (0 / 207 at C4).

## 3. Capacity per config × condition (episodic N = 1, budget p99 ≤ 0.45 s)

| config | C0 (no recall) | C1 (cold r 0.05) | C4 (KV-HOST k 8 + cold r 0.1) | C1 levels below own C0 | removes interference? |
|---|---|---|---|---|---|
| P0 default | **40 %** (top; p99 0.216 / 0.276 / 0.271 / 0.294 / 0.383 at 10 / 20 / 25 / 30 / 40 %) | **< 10 %** (2.646 s) | **< 10 %** (4.710 s) | 5 | — (control) |
| P1 threshold 1024 | **40 %** (0.280 / 0.370 at 25 / 40 %) | **< 10 %** (2.124 s) | **< 10 %** (3.499 s) | 5 | **no** |
| P2 threshold 512 | **40 %** (0.276 / 0.364) | **< 10 %** (1.978 s) | **< 10 %** (3.274 s) | 5 | **no** |
| P3 1024 + priority | **40 %** (0.272 / 0.385) | **< 10 %** (2.154 s) | **< 10 %** (3.847 s) | 5 | **no** |

"Levels below" counts < 10 % as one level under 10 %.

**V3 (text-only, token-matched), C1, episodic p99:**

| level | P0 | P1 | P2 | P3 |
|---|---|---|---|---|
| 10 % | 2.595 | 2.098 | 2.016 | 2.153 |
| 25 % | 2.253 | 2.023 | 1.976 | 1.920 |

All of these fail the budget.

**Episodic latency (s), p50 / p90 / p99, at C1 10 %:**

| config | V1 | V3 |
|---|---|---|
| P0 | 0.147 / 0.636 / 2.646 | 0.145 / 0.211 / 2.595 |
| P1 | 0.148 / 0.690 / 2.124 | 0.145 / 0.210 / 2.098 |
| P2 | 0.145 / 0.603 / 1.978 | 0.146 / 0.209 / 2.016 |
| P3 | 0.146 / 0.637 / 2.154 | 0.145 / 0.208 / 2.153 |

At C4 10 % (V1):

| config | p50 / p90 / p99 |
|---|---|
| P0 | 0.211 / 3.037 / 4.710 |
| P1 | 0.215 / 2.257 / 3.499 |
| P2 | 0.260 / 2.098 / 3.274 |
| P3 | 0.289 / 2.525 / 3.847 |

**Server side (window means).**
- GPU utilisation: 23–27 % (C1), 47–49 % (C4), 34–61 % (C0, by level).
- Computed tok/s: about 1,050 (C1 V1), 1,100 (C1 V3 10 %), 2,210 (C4), and 549 → 2,298 across the C0 ladder.
- Waiting mean: ≤ 0.03 (C1), 0.21–0.39 (C4).
- Preemptions 0 and unfinished 0 everywhere.

None of these differ by config beyond noise: the cap does not change how much work the GPU does.

**What the cap does:**
- It lowers C1 V1 p99 by 19–25 % (2.65 → 1.98–2.15 s), C4 p99 by 18–30 % (4.71 → 3.27–3.85 s), and C1 V3 p99 by 7–19 %.
- p99 stays 4–8× over the budget.
- 512 tokens helps marginally more than 1024; adding priority (P3 vs P1) does not help (C1 2.154 vs 2.124 s, C4 3.847 vs 3.499 s).

## 4. Cost to the cold recall and to warm recall (vs P0 at the same cell)

| cell | cold TTFT p50 (ratio) | cold TTFT p99 (ratio) | warm append p50 | warm escalation p50 |
|---|---|---|---|---|
| P0 C1 10 % | 3.899 | 5.582 | — | — |
| P1 C1 10 % | 4.075 (1.05) | 6.248 (1.12) | — | — |
| P2 C1 10 % | 3.972 (1.02) | 6.318 (1.13) | — | — |
| P3 C1 10 % | 4.032 (1.03) | 6.249 (1.12) | — | — |
| P0 C4 10 % | 4.449 | 6.942 | 0.318 | 0.391 |
| P1 C4 10 % | 4.944 (1.11) | 7.880 (1.14) | 0.323 | 0.396 |
| P2 C4 10 % | 5.064 (1.14) | 7.910 (1.14) | 0.435 (1.37) | 0.510 (1.30) |
| P3 C4 10 % | 5.468 (1.23) | 8.404 (1.21) | 0.488 (1.53) | 0.819 (2.09) |

- **Cold recall:** C1 V3 cold TTFT p50 rises 0–3 %, and p99 rises 1–2 % at 10 % and 25–28 % at 25 %.
- **C0 capacity:** no loss in any config (40 % kept; p99 at 40 % 0.364–0.385 vs P0 0.383).
- **Warm recall:** the cap costs warm recall at C4. P2's smaller chunks slow appends and escalations by 30–37 %. P3's priority puts warm requests (priority 1) behind episodic ones and doubles the escalation p50. Nothing starves: cold p99 is at most 8.4 s, and 0 requests are unfinished.

## 5. Release timing (E10c §6 / E10d §4 method)

C1 V1 10 %. "Slow" means an episodic TTFT above 0.45 s; "inside" means submitted in [cold sent, cold first token].

| config | slow | inside a cold window | release − cold first token p10 / p50 / p90 (s) | slow submit − cold engine arrival, p50 | frontend-phase episodic within budget |
|---|---|---|---|---|---|
| P0 | 40 | 40 | **0.00** / +0.23 / +0.42 | 1.34 s | 14 / 14 |
| P1 | 45 | 45 | **−1.19** / +0.09 / +0.26 | 1.59 s | 14 / 14 |
| P2 | 39 | 39 | **−0.97** / −0.11 / +0.21 | 1.30 s | 14 / 14 |
| P3 | 43 | 43 | **−1.24** / +0.08 / +0.21 | 1.54 s | 14 / 14 |

At C4 (all slow requests are inside cold windows, 131–147 per cell):

| config | release − cold first p10 / p50 / p90 (s) |
|---|---|
| P0 | 0.00 / +0.05 / +0.42 |
| P1 | −1.49 / −0.58 / +0.27 |
| P2 | −1.60 / −0.77 / +0.29 |
| P3 | −1.80 / −0.69 / +0.55 |

**Reading:**
- **P0:** every held episodic request is released at or after the cold first token (p10 = 0.00), as in E10c / E10d.
- **The cap does act.** Under P1–P3 the p10 release moves 1.0–1.8 s *before* the cold first token, so some held requests are now co-scheduled with the cold prefill and released mid-prefill. The effect is stronger at C4, where more requests are in the system.
- **But the number of slow requests does not fall** (39–45 vs 40 at C1). The median slow request is still released within ±0.1 s of the cold first token at C1.

**Step 3 trace** (C1 V1 10 %, the cold request with the most episodic arrivals in its engine phase; `e10e_results.json` `cells.*.trace`). Times are relative to the cold send.

| config | 'Added' | cold first | episodic submitted → TTFT (release − cold first) |
|---|---|---|---|
| P0 | 1.090 | 3.149 | +0.63 → **2.52** (+0.00); +1.48 → **2.09** (+0.42); +1.51 → **2.06** (+0.42); +1.67 → **1.90** (+0.42); +1.70 → **1.87** (+0.42); +2.36 → **1.21** (+0.42); +2.84 → **0.75** (+0.44); +2.90 → **0.69** (+0.44); +3.30 → 0.35 |
| P1 | 1.221 | 3.718 | +0.63 → **2.62** (−0.46); +1.48 → **1.78** (−0.46); +1.51 → **2.21** (+0.00); +1.67 → **2.05** (+0.00); +1.70 → **2.02** (+0.00); +2.36 → **1.36** (+0.00); +2.84 → **0.88** (+0.00); +2.90 → **0.89** (+0.08); +3.33 → **0.53** (+0.11); +4.04 → 0.17 |
| P3 | 1.654 | 6.360 (two cold prefills back to back) | +0.74 → **2.16** (−3.46); +1.01 → **1.89** (−3.46); +3.48 → **0.56** (−2.32); +3.95 → **0.53** (−1.88); +4.09 → **0.64** (−1.64); +4.24 → **0.73** (−1.39); +4.49 → **0.74** (−1.13); +5.44 → **1.06** (+0.11); +5.82 → **0.75** (+0.21) |

What the traces show:
- **P1:** two requests are released together 0.46 s *before* the cold first token, and the rest still wait for it.
- **P3, across two back-to-back cold prefills:** requests arriving during the second prefill are released one after another, 1.1–2.3 s before its first token. That is co-scheduling working. Yet each still took 0.53–0.74 s, over the 0.45-s budget.

**Why the cap does not remove the hold.** This is an inference from the timing and the source, not a per-step log.
1. **The cap is skipped while the cold request is the only one in the system** (`scheduler.py` l. 611–619), and at 10 % load it often is.
2. **Async scheduling is on by default** in vLLM 0.31.0 for this setup (`vllm/config/vllm.py` l. 1576–1635: `async_scheduling` None → True unless pooling, unsupported spec-decode or PP). So step *n + 1* is scheduled while step *n* runs, i.e. before an episodic request that arrives during step *n* is visible.
3. **The cold prefill is only two steps.** At 8,192 tokens per step a 12.6k-token prefill is 8,192 + ~4,450 tokens, so both steps are usually scheduled while the cold request is alone.

Evidence that the cap rarely binds at C1:
- The cold request's engine phase ('Added' → first token, p50) is unchanged: P0 2.46 s, P1 2.50 s, P2 2.49 s, P3 2.51 s. A binding cap of 1024 / 512 would split the prefill into 13 / 25 steps and lengthen it.
- Cold TTFT p50 rises only 2–5 % at C1.
- At C4, where warm sessions keep other requests in the system, the cap binds more often. There, cold TTFT rises 11–23 % and p99 falls more (18–30 %), as the mechanism predicts.
- Even when the cap binds (P3 trace), a co-scheduled episodic request waits for the in-flight step plus the already-scheduled one. That is 0.5–0.75 s at these step sizes, still over the 0.45 s budget.

This is the residual predicted in §1 Step 2 ("only request" exemption). Async scheduling makes it worse, and it was not named before the sweep.

## 6. Consistency protocol (6 checks)

1. **Cross-check against committed measurements.** PASS.

   | quantity | this run (P0) | prior | source | ratio | agree |
   |---|---|---|---|---|---|
   | C0 N1 p99 10 / 20 / 25 / 30 / 40 % | 0.216 / 0.276 / 0.271 / 0.294 / 0.383 | 0.225 / 0.290 / 0.279 / 0.288 / 0.387 | E10c E0 | 0.96 / 0.95 / 0.97 / 1.02 / 0.99 | yes |
   | C1 N1 10 % p99 | 2.646 | 2.739 / 2.974 | E10c E0 / E10d V1 | 0.97 / 0.89 | yes |
   | C4 N1 10 % p99 | 4.710 | 4.824 | E10c E0 | 0.98 | yes |
   | C1 V3 10 / 25 % p99 | 2.595 / 2.253 | 2.571 / 2.246 | E10d E0 V3 | 1.01 / 1.00 | yes |
   | cold TTFT p50 C1 / C4 | 3.90 / 4.45 s | 4.05 / 4.18 s | E10c E0 | 0.96 / 1.07 | yes |
   | append / escalation p50 C4 | 0.318 / 0.391 s | 0.316 / 0.363 s | E10c E0 | 1.01 / 1.08 | yes |
   | C4 GPU util / computed tok/s | 49.5 % / 2,210 | 46.1 % / 2,211 | E10c E0 | 1.07 / 1.00 | yes |
   | C0 capacity, P1–P3 vs E10c E1 / E2 / E4 | 40 % | 40 % | E10c | 1.0 | yes |

2. **Physical plausibility.** PASS.
   - The cold engine phase is 2.46–2.51 s for 12.6k tokens (≈ 5.0k tok/s including the ≈ 0.2-s encoder), consistent with E10d's 2.17-s text prefill (5.8k tok/s).
   - Computed tok/s is far below the H100 prefill rate (GPU 23–61 % busy).
   - No faster-than-curve result.
   - prefix caching ON as in E10c / E10d. Cold prompts are distinct per cell (cached_tokens 0 on cold requests); warm sessions hit as intended (0 misses).
3. **Distribution sanity.** PASS.
   - p50 / p90 / p99 are reported per cell.
   - p99 varies 0.216–4.710 s across cells.
   - The C0 p99s of P0–P3 at 40 % (0.364–0.385) differ in the 2nd decimal as cell-to-cell noise should.
   - The cold engine-phase medians agree to ±0.05 s across configs, explained in §5 by a non-binding cap, not a constant.
4. **Definition audit.** PASS.
   - Budget 0.45 s, peak 15.1 req/s, window (30-s discard, 240 s), drain cap 300 s, C0 / C1 / C4 and seeds are E10c's; V1 / V3 are E10d's.
   - "Removes the interference" = C1 capacity within one ladder level of the same config's C0 capacity (pre-registered).
   - P1–P3 C0 capacity is read from the 25 / 40 % cells only (user decision). 40 % passing is taken as capacity 40 % (ladder top), as E10c showed no lever moves C0.
5. **Claim linkage.**
   - FORMULATION's shared-replica cost.
   - **Strengthens** E10b / E10c / E10d: cold recall cannot share a replica with episodic scoring under any documented vLLM 0.31.0 scheduling control tested so far (priority, step budget, now the long-prefill cap with and without priority).
   - Isolation (own replica) or admission control remains the requirement.
   - Bounded by §7's caveat on the untested combinations.
6. **Proxy validity.**
   - Episodic p99 TTFT is the direct quantity.
   - The async-scheduling explanation is an inference from the source plus the unchanged cold engine phase. vLLM 0.31.0 logs no per-step allocation at INFO, so it is labelled as inference, not measured.

**Result: PASS 6 / 6.**

## 7. Verdict

**Decision (pre-registered): no config removes the interference.**
- P1 (threshold 1024), P2 (512) and P3 (1024 + priority) each keep C0 capacity at 40 % (the ladder top, same as P0, no C0 loss), but have C1 and C4 capacity < 10 %. That is 5 levels below their own C0, against the rule's ≤ 1.
- **By the pre-registered rule, the cold-recall interference is not removable by vLLM 0.31.0's documented scheduling controls on this stack.** E10c tested priority and a 2,048-token step budget; this run tested the long-prefill cap with and without priority.
- The two partial-prefill counters requested originally do not exist in 0.31.0 (§0).

**Cost of the controls tested.**
- Cold recall TTFT: +2–5 % p50 and +12–13 % p99 at C1; +11–23 % p50 and +14–21 % p99 at C4.
- Warm recall at C4: P2 appends / escalations +37 % / +30 %, and P3 escalation ×2.1 because priority demotes warm recall.
- No C0 capacity loss, no starvation, no preemptions.

**Rule 2 classification: real negative for the configurations tested, with the reason located.**
- The mechanism was present and exercised:
  - flags verified in 27 / 27 server logs;
  - the cap visibly co-scheduled held requests (release p10 1.0–1.8 s before the cold first token, vs 0.00 at P0);
  - it cut p99 by 18–30 %;
  - the P0 control reproduced E10c / E10d.
- It does not reach the budget because the cap applies only when another request is already in the system at schedule time. With async scheduling and an 8,192-token step, the cold prefill's two steps are usually committed before any episodic request is visible, and even a co-scheduled request waits 0.5–0.75 s.

**Caveat, stated rather than tested.** Two documented 0.31.0 options could shrink that residual, and neither was in the pre-registered design:
- a smaller step budget together with the cap (`--max-num-batched-tokens 2048 --long-prefill-token-threshold 512`), which bounds an alone step to ~2k tokens;
- `--no-async-scheduling` (the `async_scheduling` field, `config/scheduler.py` l. 209).

The verdict's "not removable" therefore covers the pre-registered controls (P1–P3) plus E10c's levers, not those combinations.
