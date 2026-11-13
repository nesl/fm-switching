# StudyE10f-engine-residual: do the two engine combinations E10e left untested remove the cold-recall interference?

E-id: StudyE10f-engine-residual (`research/EXPERIMENTS.md`, pre-registered 2026-11-12). Host: h100nvl **GPU 2**, exclusive.

## 0. Question and design (recorded before running)

**Question.** StudyE10e found that vLLM 0.31.0's long-prefill cap (`--long-prefill-token-threshold`) acts but does not restore episodic capacity under cold K1 recall. Its explanation, an inference from the source and the timing, has two parts:
- the cap is skipped while the cold request is the only request in the system (`scheduler.py` l. 611–619);
- with async scheduling (on by default, `config/vllm.py` l. 1576–1635), the 12.6k-token prefill's two 8,192-token steps are usually committed before an episodic request is visible.

E10e named two documented combinations as untested; this study runs them:

| config | flags | aims at |
|---|---|---|
| Q1 | `--max-num-batched-tokens 2048 --long-prefill-token-threshold 512` | bounds every step, including one the cold request takes alone, to 2,048 tokens (≈ 0.35 s), and leaves ≥ 1,536 tokens for others when the cap applies |
| Q2 | `--long-prefill-token-threshold 1024 --no-async-scheduling` | the next step is scheduled only after the current one finishes, so an episodic request that arrived during it is visible and the cap applies |

**Flag check (vLLM 0.31.0).**
- `--async-scheduling, --no-async-scheduling` is in `vllm serve --help=all` ("If set to False, disable async scheduling", default None).
- `EngineArgs.async_scheduling` is defined at `engine/arg_utils.py` l. 811, its argparse entry at l. 1739, and it is passed into `SchedulerConfig` at l. 2573.
- `SchedulerConfig.async_scheduling` is at `config/scheduler.py` l. 209.
- `config/vllm.py` l. 1576 resolves the default only when the value is None, so False is kept, and `get_scheduler_cls` (`config/scheduler.py` l. 230–236) returns `Scheduler`, not `AsyncScheduler`.
- `--max-num-batched-tokens` and `--long-prefill-token-threshold` were verified in E10c / E10e.
- Each server's logged non-default args are checked for threshold, step budget and `'async_scheduling': False` (Q2). The run STOPs on a mismatch.

**Harness, conditions, seeds, decision: exactly as StudyE10e.**
- `study_e10f_engine_residual.py` is `study_e10e_partial_prefill.py` with only the config table, plan, control references, output names and time guard changed. It imports `study_e10b_mixed.py` and `study_e10d_blocking.py` unchanged.
- V1 cold request (PNG video); episodic N = 1, budget p99 ≤ 0.45 s.
- C0 at 25 % and 40 %; C1 (KV-GPU, cold r 0.05) and C4 (KV-HOST k 8 + cold r 0.1) ladders 10 / 20 / 25 / 30 / 40 % of 15.1 req/s, bottom-up, stopping at the first failure.
- E10c seeds; fresh server per cell.
- **P0 control:** E0 defaults at C0 25 % and C1 10 % must reproduce E10e P0 (0.271 s and 2.646 s) within 2×, else STOP.
- **Decision:** a config removes the interference iff its C1 capacity is within one ladder level of its own C0 capacity. The report gives its cost: cold and warm recall TTFT vs E10e P0, and any C0 capacity loss.
- **Estimate:** 10–26 cells, 1.0–2.7 h. The run stops before a new cell once 2 h have elapsed and asks (user rule: stop and ask above 2 h). The upper end is reached only if a config climbs its ladders.

## 1. Mechanism verification (recorded BEFORE the sweep)

**Step 1, causal chain.**
- FORMULATION's shared-replica cost: whether cold recall can share a replica with episodic scoring. E10d located the hold in the LM prefill; E10e showed the cap co-schedules some held requests but rarely binds.
- The claimed chain for this run: if the hold is the cold prefill occupying whole steps that were committed before an episodic request arrived, then either of two changes should bring the wait down to about one short step:
  - (Q1) making every step short, alone or not, so an episodic request waits at most one 2,048-token step plus one capped step;
  - (Q2) scheduling each step only after the previous one, so the cap sees the episodic request at the next boundary.
- Once the wait is about one short step, episodic p99 falls under 0.45 s and C1 capacity returns toward C0.
- The cost: the cold prefill is split into many more steps, so cold TTFT rises. Q1 also lowers the batch budget for everything (E10c's E2 cost no C0 capacity).

**Step 2, instantiate each link.**

| link | implementing quantity | value / range | varies as needed? | evidence |
|---|---|---|---|---|
| step size when the cold request is alone | `max_num_batched_tokens` | 8,192 (P0, Q2), 2,048 (Q1) | yes, by config | server log |
| cap when others are present | `long_prefill_token_threshold` | 0 (P0), 512 (Q1), 1,024 (Q2) | yes | server log non-default args |
| step committed before arrival | `async_scheduling` | default → True (P0, Q1), False (Q2) | yes | server log non-default args (`'async_scheduling': False`) |
| long prefill present | cold K1 prompt 11.3–12.6k tokens | r 0.05 (C1), 0.1 (C4), none (C0) | yes, by condition | `prompt_tokens` |
| episodic hold | p99, slow count inside cold windows, release − cold first token | measured | to be measured | rows + server log |
| cost | cold TTFT p50 / p99, append / escalation TTFT | measured | to be measured | rows |

No link is ABSENT or CONSTANT.

**Step 3, trace one unit.**
- For one cold request per config (C1 V1 10 %), the report gives:
  - send, 'Received request', 'Added request' and first-token times;
  - the episodic requests submitted around it, with TTFT and release relative to the cold first token.
- The cold engine phase ('Added' → first token) is the direct check that the prefill is now split: it should lengthen versus P0's 2.46 s. It did **not** in E10e, which is why E10e's cap was judged non-binding.

**Step 4, negative control.**
- P0 (cap off, async on, 8,192) is the mechanism switched off; it must reproduce E10e P0.
- C0 is the no-long-prefill null for each config.

**Step 5, alternative explanations.**
- **(i) Lower load instead of a removed hold.** A config could pass C1 because the slower cold prefill overlaps fewer episodic arrivals.
  - Distinguishing evidence: slow requests inside cold windows must fall, and the remaining ones must not be released at the cold first token.
- **(ii) A residual unchunkable vision-encoder step** (≈ 0.2 s, E10d) could keep p99 above budget although the LM prefill is co-scheduled.
  - Distinguishing evidence: where the remaining slow requests sit relative to the cold engine arrival (the encoder runs in the cold request's first engine step).
- **(iii) Q1's smaller step budget alone** (E10c's E2), without the cap, did nothing. Q1 differs from E2 only by the cap, so E10c's E2 C1 result (< 10 %) is the comparison for that factor.

## 2. Run (2026-11-12 14:16 → 15:23)

- **Size:** 10 cells in 67 min (≈ 6.7 min per cell), inside the 1.0–2.7 h estimate. Both configs stopped at C1 / C4 10 %, so the 2-h guard was not reached.
- **Exclusivity:** 142 monitor samples; foreign process on GPU 2 in 0, our processes outside the job in 0. **Not VOID.**
- **Flags verified in 10 / 10 server logs:**

  | config | `long_prefill_token_threshold` | `max_num_batched_tokens` | `async_scheduling` |
  |---|---|---|---|
  | P0 | 0 | 8192 | default |
  | Q1 | 512 | 2048 | default |
  | Q2 | 1024 | 8192 | **False** |

  All ran fcfs with chunked prefill on.
- **Control gate:** PASS. P0 C0 25 % gave 0.274 s against E10e P0 0.271 s (ratio 1.01). P0 C1 10 % gave 2.670 s against 2.646 s (1.01).
- **Errors:** cold prompts were token-exact and every cold request was found in the server log. 0 episodic errors, 0 preemptions, 0 unfinished, 0 / 207 warm misses at C4.

## 3. Capacity per config × condition (episodic N = 1, budget p99 ≤ 0.45 s)

| config | C0 (no recall) | C1 (cold r 0.05) | C4 (KV-HOST k 8 + cold r 0.1) | C1 levels below own C0 | removes interference? |
|---|---|---|---|---|---|
| P0 (control; E10e P0 for the full ladders) | 25 % run, 0.274 s (E10e: 40 %) | < 10 % (2.670 s) | (E10e: < 10 %, 4.710 s) | — | — |
| **Q1** 2048 + cap 512 | **40 %** (0.276 / 0.350 s at 25 / 40 %) | **< 10 %** (**0.919 s**) | **< 10 %** (**1.294 s**) | 5 | **no** |
| **Q2** cap 1024 + async off | **40 %** (0.309 / 0.416 s) | **< 10 %** (2.014 s) | **< 10 %** (2.691 s) | 5 | **no** |

**Episodic p50 / p90 / p99 (s) at 10 %:**

| config | C1 | C4 |
|---|---|---|
| P0 | 0.146 / 0.775 / 2.670 | — |
| Q1 | 0.146 / 0.424 / 0.919 | 0.205 / 0.790 / 1.294 |
| Q2 | 0.145 / 0.449 / 2.014 | 0.204 / 1.686 / 2.691 |

**Reading:**
- **Q1 is the first engine setting in E10c–E10f that moves the cold-recall tail substantially.** C1 p99 drops 2.9× vs P0 (2.67 → 0.92 s) and C4 p99 drops 3.6× vs E10e P0 (4.71 → 1.29 s). C1 p90 is under budget (0.424 s). It still fails the 0.45-s p99 by 2×, so its capacity under recall stays < 10 %.
- **Q2 helps no more than E10e's cap alone** (C1 2.01 s vs E10e P1 2.12 s).

**Server side (window means).**
- GPU utilisation: 23–26 % at C1, 46–49 % at C4.
- Computed tok/s: about 1,050 at C1 and 2,208 at C4, the same as E10e.
- Waiting mean ≤ 0.23. 0 preemptions, 0 unfinished.

## 4. Cost to cold and warm recall (vs E10e P0 at the same cell)

| cell | cold TTFT p50 (ratio) | cold TTFT p99 (ratio) | warm append p50 (E10e P0 0.318) | warm escalation p50 (E10e P0 0.391) |
|---|---|---|---|---|
| Q1 C1 10 % | 4.253 (1.09) | 6.660 (1.19) | — | — |
| Q2 C1 10 % | 4.216 (1.08) | 6.135 (1.10) | — | — |
| Q1 C4 10 % | 4.797 (1.08) | 7.748 (1.12) | 0.313 | 0.338 |
| Q2 C4 10 % | 4.655 (1.05) | 7.625 (1.10) | 0.313 | 0.341 |

- **Cold recall:** 5–9 % slower at the median and 10–19 % at p99.
- **Warm recall:** unchanged, or slightly faster. Q1's smaller steps help short warm requests: escalation 0.338 vs 0.391 s.
- **No C0 loss:** both configs hold 40 %. Q1 is even lower at 40 % (0.350 vs E10e P0 0.383 s); Q2 is slightly higher (0.416 s), still under budget.

## 5. Release timing (E10c §6 / E10d §4 method)

"Slow" means an episodic TTFT above 0.45 s.

| cell | slow | inside a cold window | release − cold first p10 / p50 / p90 (s) | cold engine phase p50 ('Added' → first token) |
|---|---|---|---|---|
| P0 C1 10 % | 43 | 42 | 0.00 / +0.22 / +0.43 | 2.46 s |
| Q1 C1 10 % | 33 | 33 | **−2.15 / −0.76** / +0.13 | **2.66 s** |
| Q2 C1 10 % | 35 | 35 | −1.14 / −0.57 / +0.15 | 2.63 s |
| Q1 C4 10 % | 100 | 100 | **−2.90 / −1.65** / +0.01 | 3.26 s |
| Q2 C4 10 % | 126 | 126 | −1.50 / −0.88 / −0.17 | 3.17 s |

Compare E10e at C1:
- E10e P1 had release p50 +0.09 and an engine phase of 2.50 s;
- E10e P0 had 2.46 s.

**Reading:**
- **Both configs now release the median slow request *before* the cold first token**, unlike E10e P1–P3, whose median was at the first token. The cold engine phase also lengthens (2.46 → 2.63–2.66 s at C1). So the prefill is now split and episodic requests are co-scheduled.
- **Fewer requests are slow:** 33–35 vs 43.
- **Q1's held requests come out earliest** (p10 −2.15 s): with 2,048-token steps they wait at most about one short step.

**Step 3 trace** (C1 V1 10 %, the cold request with the most episodic arrivals in its engine phase; times from the cold send; submitted → TTFT (release − cold first)):

| config | 'Added' | cold first | episodic |
|---|---|---|---|
| Q1 | 1.761 | 6.787 (two cold prefills back to back) | +0.74 → **1.00**; +1.01 → **0.74**; +3.48 → **0.52** (−2.79); +3.95 → 0.28 (−2.56); +4.09 → 0.40; +4.24 → 0.39; +4.53 → 0.39; +5.41 → **0.62** (−0.76); +5.82 → **0.50**; +6.09 → 0.40; +6.36 → 0.43 (+0.00); +6.87 → 0.13 |
| Q2 | 1.158 | 3.698 | +0.62 → **2.75** (−0.33); +1.47 → **1.90** (−0.33); +1.50 → **1.87**; +1.66 → **1.71**; +1.70 → **1.68**; +2.35 → **1.02** (−0.33); +2.83 → **0.87** (+0.00); +2.89 → **0.81**; +3.29 → 0.41; +4.03 → 0.10 |

What the traces show:
- **Q1:** most episodic requests inside the cold prefill are served in 0.28–0.43 s, under budget, while the prefill continues.
  - The ones over budget arrived during the API-server processing tail of the cold request or at the cold request's first engine steps (+0.74 / +1.01 s, before 'Added' at 1.76 s). They waited for the ≈ 0.2-s vision-encoder step plus the first 2,048-token steps.
  - A few mid-prefill requests took 0.50–0.62 s.
- **Q2:** requests arriving in the first ~2.4 s of the engine phase are all released together, 0.33 s before the cold first token.
  - That is the shape of one long alone-step. With async off, the cap still does not apply while the cold request is alone, and an 8,192-token alone-step takes about 1.4 s plus the encoder.
  - Turning async scheduling off alone does not remove E10e's residual. The step size does.

**Why Q1 still fails (inference from the traces).** The remaining tail is the cold request's *first* engine step(s):
- the unchunkable vision-encoder pass (≈ 0.2 s, E10d);
- a 2,048-token step taken while the cold request is alone;
- the already-scheduled next step.

Together these reach 0.5–1.0 s for an episodic request that arrives just before or at the cold engine arrival. E10d's frontend-tail effect (arrivals in the last ~0.7 s of the cold request's API-server processing are delayed into its engine phase) adds to the same cases.

## 6. Consistency protocol (6 checks)

1. **Cross-check against committed measurements.** PASS.

   | quantity | this run | prior | source | ratio | agree |
   |---|---|---|---|---|---|
   | P0 C0 N1 25 % p99 | 0.274 s | 0.271 s | E10e P0 | 1.01 | yes |
   | P0 C1 N1 10 % p99 | 2.670 s | 2.646 s | E10e P0 | 1.01 | yes |
   | P0 cold engine phase p50 | 2.46 s | 2.46 s | E10e P0 | 1.00 | yes |
   | Q2 C1 10 % p99 (cap 1024) | 2.014 s | 2.124 s | E10e P1 (cap 1024, async on) | 0.95 | yes |
   | C1 / C4 computed tok/s | 1,048–1,051 / 2,208 | 1,050 / 2,210 | E10e P0 | 1.00 | yes |
   | C4 append p50 | 0.313 s | 0.318 s | E10e P0 | 0.98 | yes |
   | C0 capacity | 40 % | 40 % | E10c / E10e | 1.0 | yes |

2. **Physical plausibility.** PASS.
   - The cold engine phase is 2.63–2.66 s for 12.6k tokens (≈ 4.8k tok/s including the encoder), consistent with E10d's 5.8k tok/s text-only prefill and slightly slower, as expected for a split prefill.
   - GPU utilisation is ≤ 49 %. No faster-than-curve result.
   - Prefix caching ON, as in E10c–e. Cold prompts are distinct.
3. **Distribution sanity.** PASS.
   - p50 / p90 / p99 are reported per cell. p99 varies 0.274–2.691 s.
   - Cold engine-phase medians differ by config in the predicted direction.
   - No constants where distributions are expected.
4. **Definition audit.** PASS. Budget, peak, levels, window, drain cap, conditions, seeds, the V1 cold request and the decision rule are identical to E10e (§0). C0 for Q1 / Q2 was run at 25 / 40 % as in E10e P1–P3.
5. **Claim linkage.**
   - FORMULATION's shared-replica cost.
   - **Strengthens** E10b–E10e: no documented vLLM 0.31.0 scheduling control or tested combination lets cold recall share a replica with episodic scoring at the 0.45-s p99 budget.
   - **Also shows the interference is reducible:** Q1 cuts the tail ≈ 3×, with C1 p90 under budget. The remainder sits in the cold request's first engine steps, i.e. the encoder plus one alone-step.
6. **Proxy validity.**
   - Episodic p99 TTFT is the direct quantity.
   - The location of the residual (first step: encoder plus an alone-step) is an inference from request timing. vLLM 0.31.0 logs no per-step allocation, so it is labelled as inference.

**Result: PASS 6 / 6.**

## 7. Verdict

**Decision (pre-registered): neither config removes the interference.** Q1 and Q2 keep C0 capacity at 40 % (no loss) but have C1 and C4 capacity < 10 %, five levels below their own C0, against the rule's ≤ 1.

**Rule 2 classification: real negative, mechanism present and exercised.**
- Flags were verified in every server log.
- Both configs now split the prefill: the cold engine phase lengthens and held requests are released mid-prefill (median 0.57–0.76 s before the cold first token at C1).
- **Q1 cuts the episodic tail about 3×** (C1 p99 2.67 → 0.92 s; C4 4.71 → 1.29 s) at a cold-recall cost of +8–9 % p50 / +12–19 % p99, with no warm-recall or C0 cost.
- **Q2 (async off) adds nothing over E10e's cap.** While the cold request is alone its steps stay 8,192 tokens, so turning async off does not remove the residual.

**With E10c–E10e this closes the engine-side question for vLLM 0.31.0.** None of these scheduling settings or tested combinations brings episodic p99 under 0.45 s while a cold K1 recall runs on the same replica:
- priority;
- step budget 2,048;
- long-prefill cap 512 / 1024, with and without priority;
- cap + 2,048 step budget;
- cap + async off.

The best (Q1) leaves a tail of about 0.9–1.3 s, located in the cold request's first engine steps. Cold recall still needs isolation or admission control (StudySLICE1 tests orchestrator-level slicing).
